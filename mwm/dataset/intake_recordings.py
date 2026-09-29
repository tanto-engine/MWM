"""Index Recorder folders without promoting unreviewed actions to playable moves."""
import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parent
PRODUCT = ROOT.parent
BUILD = json.loads((PRODUCT / 'data/moves.json').read_text(encoding='utf8'))['supported_build_sha256']
BLOCKERS = ['actor_and_phase_mapping_unreviewed', 'william_adapter_unverified',
            'motion_timing_resources_unverified', 'gameplay_unverified']


def digest(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value, compact=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf8', newline='\n') as output:
        output.write(json.dumps(value, indent=None if compact else 2,
                                separators=(',', ':') if compact else None, ensure_ascii=True) + '\n')


def archive(raw):
    # Stable member order and timestamps make repeated intake idempotent.
    # The archive retains original member bytes, including transient pointers.
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as target:
        for name, data in sorted(raw.items()):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            target.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return stream.getvalue()


def title(note):
    return re.sub(r'^\s*Sword\s*/\s*', '', note, flags=re.I).strip()


def candidate_id(boss, note):
    # UUID suffix keeps two similarly named takes distinct until a reviewer links them.
    slug = re.sub(r'[^a-z0-9]+', '_', title(note['text']).lower()).strip('_')[:64].rstrip('_')
    return f"sword.{boss}.recorded_{slug}_{note['id'][:8]}"


def import_folder(folder, dataset, catalogue, intake):
    # Each session is indexed once; old curated records remain authoritative.
    # A saved annotation becomes a named, unplayable candidate with immutable evidence.
    # No actor ownership, combo phase or player adaptation is inferred from its prose.
    raw = {name: (folder / name).read_bytes() for name in ('encounter.json', 'events.jsonl') if (folder / name).is_file()}
    encounter = json.loads(raw['encounter.json'])
    if encounter['boss_name'] == 'Edward Kelley':
        return 'excluded'
    existing = {row['recording_id']: row for row in intake['sessions']}
    if encounter['recording_id'] in existing:
        if existing[encounter['recording_id']]['files'] != {name: digest(data) for name, data in raw.items()}:
            raise ValueError(f'{folder}: previously indexed session changed')
        return 'existing'
    boss = encounter['boss_name'].lower().replace('totoyomi', 'toyotomi').replace(' ', '_')
    if encounter['annotations']:
        dataset['bosses'].setdefault(boss, {'name': encounter['boss_name'].replace('Totoyomi', 'Toyotomi')})
        if not any(row['id'] == boss for row in catalogue['bosses']):
            catalogue['bosses'].append({'id': boss, 'name': dataset['bosses'][boss]['name']})
    packed = archive(raw)
    archive_hash = digest(packed)
    target = ROOT / 'evidence' / f'{archive_hash}.zip'
    if target.exists() and target.read_bytes() != packed:
        raise ValueError(f'{folder}: archive hash collision')
    target.write_bytes(packed)
    events = Counter()
    sessions = {}
    if 'events.jsonl' in raw:
        for number, line in enumerate(raw['events.jsonl'].splitlines(), 1):
            if not line.strip():
                continue
            row = json.loads(line)
            events[row['kind']] += 1
            if row.get('build_sha256') and row.get('take') not in sessions:
                sessions[row['take']] = (number, row['build_sha256'])
    notes = []
    known_ids = {move['id'] for move in catalogue['moves']}
    for note in encounter['annotations']:
        identifier = candidate_id(boss, note)
        if identifier in known_ids:
            raise ValueError(f'{folder}: duplicate candidate ID {identifier}')
        observed = sessions.get(note['take'])
        if observed and observed[1] != BUILD:
            raise ValueError(f'{folder}: annotation belongs to an unsupported game build')
        blockers = BLOCKERS + (['recorded_take_missing'] if observed is None else [])
        known_ids.add(identifier)
        evidence = {'archive_sha256': archive_hash, 'files': {name: digest(data) for name, data in raw.items()},
                    'recording_id': encounter['recording_id'], 'take_id': note['take'],
                    'annotation_id': note['id'], 'annotation_text': note['text'],
                    'annotation_end_seconds': note['end_t'],
                    'game_build_sha256': observed[1] if observed else None,
                    'identity_line': observed[0] if observed else None, 'steps': [], 'native_links': []}
        move = {'schema_version': 1, 'id': identifier, 'name': title(note['text']),
                'weapon_id': 'sword', 'boss_id': boss, 'kind': 'move_string',
                'review_status': 'candidate', 'priority': None, 'description': title(note['text']),
                'mapping_status': 'unmapped', 'steps': [], 'observed_links': [],
                'capture_context': {'actor_identity': 'Unverified; all actors remain in the raw recording.',
                                    'weapon_classification': 'User-described sword destination; equipped weapon unverified.'},
                'blocked_reasons': blockers, 'evidence': [evidence]}
        save(ROOT / 'weapons' / 'sword' / boss / f'{identifier.rsplit(".", 1)[1]}.json', move)
        catalogue['moves'].append({'id': identifier, 'name': move['name'], 'boss_id': boss,
                                   'weapon': 'sword', 'designation': 'unclassified',
                                   'source': {'action_id': None, 'motion_id': None, 'timing_id': None},
                                   'implementation': {'selectable': False, 'engine_profile': None},
                                   'verification': {'gameplay': 'pending'},
                                   'blocked_reasons': blockers,
                                   'evidence': [{'path': f'dataset/weapons/sword/{boss}/{identifier.rsplit(".", 1)[1]}.json',
                                                 'kind': 'recorded_candidate'}], 'default_binding': None})
        notes.append({'id': note['id'], 'text': note['text'], 'take_id': note['take'],
                      'end_seconds': note['end_t'], 'move_ids': [identifier]})
    intake['sessions'].append({'source_folder': folder.name, 'recording_id': encounter['recording_id'],
                               'source_boss_name': encounter['boss_name'], 'boss_id': boss,
                               'weapon_id': 'sword', 'archive_sha256': archive_hash,
                               'files': {name: digest(data) for name, data in raw.items()},
                               'take_count': len(encounter['takes']),
                               'recorded_action_rows': sum(take['actions'] for take in encounter['takes']),
                               'journal_event_counts': dict(events), 'status': 'unmapped_candidate',
                               'annotations': notes, 'draft': encounter['draft']})
    return 'imported'


def signature_review(intake):
    # Surface reused action numbers in the named encounter context for later actor review.
    # Full payload hashes distinguish different sources with the same short action number.
    # Raw roles are unassigned; these collisions cannot be resolved by a boss label alone.
    groups = {}
    for session in intake['sessions']:
        if session['status'] != 'unmapped_candidate':
            continue
        source = ROOT / 'evidence' / f"{session['archive_sha256']}.zip"
        with zipfile.ZipFile(source) as packed:
            for line, raw in enumerate(packed.read('events.jsonl').splitlines(), 1):
                row = json.loads(raw)
                if row['kind'] != 'metadata' or not row.get('action_key_u32') or not row.get('payload_prefix', {}).get('bytes'):
                    continue
                prefix = row['payload_prefix']
                key = (session['boss_id'], row['action_key_u32'])
                signature = (prefix['motion_id'], prefix['timing_id'], digest(bytes.fromhex(prefix['bytes'])))
                entries = groups.setdefault(key, {})
                if signature not in entries:
                    entries[signature] = {'motion_id': signature[0], 'timing_id': signature[1],
                                          'payload_prefix_sha256': signature[2], 'observations': 0,
                                          'recording_id': session['recording_id'], 'journal_line': line,
                                          'recording_ids': []}
                entries[signature]['observations'] += 1
                if session['recording_id'] not in entries[signature]['recording_ids']:
                    entries[signature]['recording_ids'].append(session['recording_id'])
    conflicts = [{'boss_id': boss, 'action_id': action, 'action_hex': f'{action:08X}',
                  'signatures': [{key: value for key, value in row.items() if key != 'recording_ids'}
                                 for row in signatures.values()]}
                 for (boss, action), signatures in sorted(groups.items()) if len(signatures) > 1]
    index = [{'boss_id': boss, 'action_id': action, 'action_hex': f'{action:08X}', **row}
             for (boss, action), signatures in sorted(groups.items()) for row in signatures.values()]
    return ({'schema_version': 1, 'scope': 'named_encounter_context_not_proven_actor',
             'distinct_boss_action_keys': len(groups), 'keys_with_multiple_signatures': len(conflicts),
             'conflicts': conflicts},
            {'schema_version': 1, 'scope': 'unmapped_sessions_named_encounter_context_not_proven_actor_or_weapon',
             'distinct_signatures': len(index), 'signatures': index})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('recordings', type=Path)
    args = parser.parse_args()
    dataset = json.loads((ROOT / 'dataset.json').read_text(encoding='utf8'))
    intake = json.loads((ROOT / 'intake.json').read_text(encoding='utf8'))
    catalogue = json.loads((PRODUCT / 'data/moves.json').read_text(encoding='utf8'))
    counts = Counter()
    for folder in sorted(args.recordings.iterdir()):
        if folder.is_dir() and (folder / 'encounter.json').is_file():
            counts[import_folder(folder, dataset, catalogue, intake)] += 1
    save(ROOT / 'dataset.json', dataset)
    save(ROOT / 'intake.json', intake)
    save(PRODUCT / 'data/moves.json', catalogue)
    review, index = signature_review(intake)
    save(ROOT / 'signature-review.json', review)
    save(ROOT / 'unmapped-action-index.json', index, compact=True)
    print(json.dumps(dict(counts, total_sessions=len(intake['sessions']),
                          sword_candidates=sum(move.get('mapping_status') == 'unmapped' for path in (ROOT / 'weapons/sword').glob('*/*.json')
                                               for move in [json.loads(path.read_text(encoding='utf8'))]))))


if __name__ == '__main__':
    main()
