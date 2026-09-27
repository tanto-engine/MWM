"""Validate the research dataset and, optionally, its immutable recording evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile


def require(condition, message):
    # Report a broken data contract without silently repairing a research claim.
    # Use exceptions rather than assertions, which Python can disable in optimized runs.
    # Callers can show the same failures in future authoring tools.
    if not condition:
        raise ValueError(message)


def load_dataset(root):
    # Load one record per weapon/boss/move path and index stable IDs for direct lookup.
    # Ordered steps define a string; their names remain hypotheses until reviewed.
    # This loader never modifies the separate legacy runtime catalogue or enables gameplay.
    root = Path(root)
    manifest = json.loads((root / 'dataset.json').read_text(encoding='utf8'))
    require(manifest.get('schema_version') == 1, 'Unsupported dataset version')
    records = {}
    for path in sorted((root / 'weapons').glob('*/*/*.json')):
        move = json.loads(path.read_text(encoding='utf8'))
        weapon, boss, filename = path.relative_to(root / 'weapons').parts
        identifier = '.'.join((weapon, boss, Path(filename).stem))
        require(all(re.fullmatch(r'[a-z][a-z0-9_]*', part) for part in identifier.split('.')), f'{path}: invalid identity')
        require(move.get('schema_version') == 1 and move.get('id') == identifier, f'{path}: identity/version mismatch')
        require(identifier not in records, f'Duplicate identity: {identifier}')
        require(weapon in manifest['weapons'] and boss in manifest['bosses'], f'{identifier}: unknown weapon/boss')
        require(move['weapon_id'] == weapon and move['boss_id'] == boss, f'{identifier}: folder classification mismatch')
        require(move['kind'] == 'move_string' and bool(move['name'].strip()), f'{identifier}: unnamed move string')
        require(move['review_status'] in ('candidate', 'reviewed', 'rejected'), f'{identifier}: invalid review status')
        require(move['priority'] in (None, 'low', 'mid', 'high'), f'{identifier}: invalid priority')
        steps = move['steps']
        require(bool(steps) and len({step['id'] for step in steps}) == len(steps), f'{identifier}: missing/duplicate steps')
        for step in steps:
            source = step['source']
            require(re.fullmatch(r'0x[0-9A-F]{8}', source['action_id']) is not None, f'{identifier}: expected full DWORD action ID')
            require(all(type(source[field]) is int for field in ('motion_id', 'timing_id')), f'{identifier}: invalid motion/timing')
            require(set(source) == {'action_id', 'motion_id', 'timing_id'}, f'{identifier}: only stable source IDs belong here')
        positions = {step['id']: index for index, step in enumerate(steps)}
        for link in move['observed_links']:
            require(link['from'] in positions and link['to'] in positions and positions[link['to']] == positions[link['from']] + 1,
                    f'{identifier}: link must join consecutive steps')
        require(bool(move['evidence']), f'{identifier}: evidence reference required')
        for evidence in move['evidence']:
            hashes = [evidence['archive_sha256'], evidence['game_build_sha256'], *evidence['files'].values()]
            require(all(re.fullmatch(r'[0-9a-f]{64}', value) for value in hashes), f'{identifier}: invalid SHA256')
            require(set(evidence['files']) == {'encounter.json', 'events.jsonl'}, f'{identifier}: unexpected evidence files')
            require([step['step_id'] for step in evidence['steps']] == list(positions), f'{identifier}: evidence step order mismatch')
            expected = {(link['from'], link['to']) for link in move['observed_links'] if 'native_transition_target' in link['basis']}
            require({(link['from'], link['to']) for link in evidence['native_links']} == expected, f'{identifier}: native link references mismatch')
            require(len(evidence['native_links']) == len(expected) and all(type(link['transition_entry_index']) is int and
                    link['transition_entry_index'] >= 0 for link in evidence['native_links']), f'{identifier}: invalid native link index')
            lines = [evidence['identity_line'], *[row[key] for row in evidence['steps'] for key in ('action_line', 'metadata_line')]]
            require(all(type(line) is int and line > 0 for line in lines), f'{identifier}: invalid evidence line')
        records[identifier] = move
    return records


def verify_evidence(records, evidence_root):
    # Hash each archive and stream each journal once, even when several moves cite it.
    # Retain only referenced rows; long fights do not require loading the entire journal.
    # Check observed identities and ordering, without pretending to verify visual move names.
    jobs = {}
    for move in records.values():
        for evidence in move['evidence']:
            jobs.setdefault(evidence['archive_sha256'], []).append((move, evidence))
    for digest, references in jobs.items():
        path = Path(evidence_root) / (digest + '.zip')
        hasher = hashlib.sha256()
        with path.open('rb') as file:
            while block := file.read(1024 * 1024):
                hasher.update(block)
        require(hasher.hexdigest() == digest, f'{path.name}: archive hash mismatch')
        wanted = {ref['identity_line'] for _, ref in references}
        wanted.update(row[key] for _, ref in references for row in ref['steps'] for key in ('action_line', 'metadata_line'))
        selected = {}
        with zipfile.ZipFile(path) as archive:
            require(sorted(archive.namelist()) == ['encounter.json', 'events.jsonl'], f'{path.name}: unexpected archive members')
            encounter_bytes = archive.read('encounter.json')
            encounter = json.loads(encounter_bytes)
            journal_hash = hashlib.sha256()
            with archive.open('events.jsonl') as journal:
                for number, raw in enumerate(journal, 1):
                    journal_hash.update(raw)
                    if number in wanted:
                        selected[number] = json.loads(raw)
        actual_hashes = {'encounter.json': hashlib.sha256(encounter_bytes).hexdigest(), 'events.jsonl': journal_hash.hexdigest()}
        for move, ref in references:
            require(actual_hashes == ref['files'], f"{move['id']}: evidence member hash mismatch")
            require(encounter['recording_id'] == ref['recording_id'], f"{move['id']}: wrong session")
            note = next((row for row in encounter['annotations'] if row['id'] == ref['annotation_id']), None)
            require(note and (note['take'], note['text'], note['end_t']) ==
                    (ref['take_id'], ref['annotation_text'], ref['annotation_end_seconds']), f"{move['id']}: annotation mismatch")
            identity = selected[ref['identity_line']]
            require(identity['take'] == ref['take_id'] and identity['build_sha256'] == ref['game_build_sha256'], f"{move['id']}: build mismatch")
            observed = {}
            for step, location in zip(move['steps'], ref['steps']):
                action, metadata = selected[location['action_line']], selected[location['metadata_line']]
                require(action['kind'] == 'action_state' and metadata['kind'] == 'metadata', f"{move['id']}: incorrect row types")
                require(action['take'] == metadata['take'] == ref['take_id'], f"{move['id']}: take mismatch")
                require(action['object'] == metadata['object'] and action['current'] == metadata['address'] and
                        metadata['matches_preceding_state'], f"{move['id']}: incoherent metadata")
                require(action['descriptor']['action_key_hex'] == metadata['action_key_hex'] == step['source']['action_id'], f"{move['id']}: action mismatch")
                require(all(metadata['payload_prefix'][key] == step['source'][key] for key in ('motion_id', 'timing_id')), f"{move['id']}: motion/timing mismatch")
                require(action['t'] == location['first_observed_seconds'] and action['counter'] == location['counter'], f"{move['id']}: observation mismatch")
                require(action['t'] <= ref['annotation_end_seconds'], f"{move['id']}: observation after annotation endpoint")
                observed[step['id']] = (action, metadata)
            for link in move['observed_links']:
                first, second = observed[link['from']][0], observed[link['to']][0]
                require(first['object'] == second['object'] and first['owner_like'] == second['owner_like'], f"{move['id']}: string crosses actors")
                require(first['t'] < second['t'], f"{move['id']}: steps are out of order")
                if 'consecutive_observed_action_counters' in link['basis']:
                    require(first['counter'] + 1 == second['counter'], f"{move['id']}: steps are not consecutive observations")
            for native in ref['native_links']:
                target = observed[native['from']][1]['transition_entries'][native['transition_entry_index']]['target_key_0x14_i16'] & 0xffff
                require(target == observed[native['to']][0]['descriptor']['action_key_u32'], f"{move['id']}: native link mismatch")
    return len(jobs)


def main():
    # Validate structure by default, with optional full provenance checks against an external archive store.
    # Print a compact index grouped by weapon and boss for humans and future tools.
    # A successful result validates stored evidence, not gameplay or a move-name hypothesis.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--evidence-root', type=Path)
    args = parser.parse_args()
    records = load_dataset(args.root)
    store = args.evidence_root or args.root / 'evidence'
    verified = verify_evidence(records, store) if args.evidence_root is not None or store.is_dir() else None
    groups = {}
    for move in records.values():
        groups.setdefault(move['weapon_id'], {}).setdefault(move['boss_id'], []).append({'id': move['id'], 'name': move['name'], 'status': move['review_status']})
    print(json.dumps({'moves': len(records), 'evidence_archives_verified': verified, 'weapons': groups}, indent=2))


if __name__ == '__main__':
    main()
