# Read/validate the sword catalogue and enrich its retained source evidence.
#
# Import never adds an unclassified move or overwrites curated names/adaptation.
# Runtime process/object/resource addresses do not belong in this file format.
# TODO: Stabilize retained sword actions before curating further source identities;
# Jin/Maria capture alone does not implement player adaptation or recovery.
import argparse
import copy
import hashlib
import json
import re
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[1] / 'outputs/Nioh1-Sword-Move-Observations.xlsx'
CATALOGUE_CACHE = None
ID = re.compile(r'^[a-z0-9][a-z0-9_.-]*$')
ADDRESS_KEYS = {'address','object','owner','owner_like','current','previous','payload','pointer','ptr','pid','module_base','descriptor_bytes'}


def iter_moves(catalogue):
    # Keep one catalogue entry per string and retain its source actions beneath it.
    # Yield stable per-action identities for adapters and evidence readers.
    # Nested constituents never become independent configuration choices.
    for move in catalogue['moves']:
        yield move
        yield from iter_moves({'moves': move.get('steps', [])})


def validate_catalogue(data):
    # Enforce stable move identities before edits reach disk.
    # Check source types, bindings and nested address fields in one pass.
    # Reject malformed records rather than silently enabling an adapter.
    if data.get('schema_version') != 1:
        raise ValueError('Unsupported catalogue schema_version')
    bosses = {boss['id'] for boss in data['bosses']}
    if len(bosses) != len(data['bosses']):
        raise ValueError('Duplicate boss ID')
    seen = set()
    for move in iter_moves(data):
        key = move['id']
        if not ID.fullmatch(key) or key in seen:
            raise ValueError(f'Invalid or duplicate move ID: {key}')
        seen.add(key)
        if move['boss_id'] not in bosses:
            raise ValueError(f'Unknown boss for {key}')
        if move.get('weapon') != 'sword':
            raise ValueError(f'{key}: catalogue supports sword data only')
        if any(step['boss_id'] != move['boss_id'] or step.get('weapon') != move.get('weapon') for step in move.get('steps', [])):
            raise ValueError(f'{key}: string constituents must share boss and weapon')
        if move.get('designation', 'unclassified') not in ('normal', 'quick', 'heavy', 'skill', 'grab', 'unclassified'):
            raise ValueError(f'{key}: unknown move designation')
        source = move['source']
        for field in ('action_id','observed_word0_u16','motion_id','timing_id'):
            value = source.get(field)
            if value is not None and (not isinstance(value,int) or isinstance(value,bool)):
                raise ValueError(f'{key}: {field} must be an integer or null')
        action = source.get('action_id')
        if action is not None and not 0 <= action <= 0xFFFFFFFF:
            raise ValueError(f'{key}: action ID outside DWORD range')
        if action is not None and source.get('action_hex') != f'{action:04X}':
            raise ValueError(f'{key}: inconsistent action_hex')
        if move['implementation'].get('selectable'):
            if action is None or source.get('motion_id') is None or source.get('timing_id') is None:
                raise ValueError(f'{key}: selectable move requires action/motion/timing IDs')
            if not move['implementation'].get('engine_profile'):
                raise ValueError(f'{key}: selectable move requires engine profile')
        binding = move.get('default_binding')
        if binding:
            if binding.get('gesture') not in ('tap_release','hold','held_chain','native_attack','native_skill','double_tap') or not binding.get('chord'):
                raise ValueError(f'{key}: invalid binding')
            if binding['gesture'] == 'native_attack':
                # Native attack replacements follow accepted stance-specific action descriptors.
                # Keep the recorded sword chain position explicit rather than inventing a timed chord.
                # This catalogue binding cannot imply a free-standing controller gesture.
                if (binding.get('stance') != 'low' or binding.get('weapon') != 'sword'
                        or type(binding.get('chain_position')) is not int or not 1 <= binding['chain_position'] <= 3):
                    raise ValueError(f'{key}: invalid native attack context')
            elif binding['gesture']=='double_tap' and not 0<binding.get('window_seconds',0)<=1.5:
                raise ValueError(f'{key}: invalid double-tap window')
            elif binding['gesture'] not in ('held_chain','native_skill','double_tap') and not 0 < binding.get('hold_seconds',0) <= 5:
                raise ValueError(f'{key}: invalid hold threshold')
        # Evidence can refer to old logs by path/line; never copy address fields.
        def no_addresses(value):
            # Keep transient runtime pointers out of permanent move records.
            # Walk nested mappings and lists for forbidden address-field names.
            # Evidence paths remain available without making pointers identities.
            if isinstance(value,dict):
                for field, nested in value.items():
                    if field.lower() in ADDRESS_KEYS:
                        raise ValueError(f'{key}: transient field {field} does not belong in catalogue')
                    no_addresses(nested)
            elif isinstance(value,list):
                for nested in value:
                    no_addresses(nested)
        no_addresses(move)
    return data


def load_catalogue(path=DEFAULT_PATH):
    # Read the single maintained workbook through its catalogue schema gate.
    # Reuse parsed cells only while the file identity, timestamp and size match.
    # Return an independent copy so a caller cannot mutate another reader's catalogue.
    if __package__:
        from .spreadsheet_sync import read_workbook_catalogue
    else:
        from spreadsheet_sync import read_workbook_catalogue
    global CATALOGUE_CACHE
    path = Path(path).resolve()
    info = path.stat()
    signature = (path, info.st_ino, info.st_mtime_ns, info.st_size)
    if CATALOGUE_CACHE is None or CATALOGUE_CACHE[0] != signature:
        CATALOGUE_CACHE = (signature, validate_catalogue(read_workbook_catalogue(path)))
    return copy.deepcopy(CATALOGUE_CACHE[1])


def save_catalogue(path, data):
    # Commit catalogue changes and their visible workbook views together.
    # Reuse the maintained workbook as the layout when creating a temporary copy.
    # Canonical edits also synchronize the user's Downloads copy.
    if __package__:
        from .spreadsheet_sync import write_workbook_catalogue
    else:
        from spreadsheet_sync import write_workbook_catalogue
    path = Path(path).resolve()
    write_workbook_catalogue(path, data, None if path == DEFAULT_PATH else False, DEFAULT_PATH)


def rename_move(catalogue_path, move_id, name, category=None):
    # Change a human label without changing the move identity.
    # Find the stable ID and validate the supplied name and category.
    # Bindings, adaptation and verification survive editorial changes.
    if not isinstance(name,str) or not name.strip() or len(name.strip())>120:
        raise ValueError('Move name must contain 1-120 characters')
    data=load_catalogue(catalogue_path)
    move=next((m for m in iter_moves(data) if m['id']==move_id),None)
    if move is None:
        raise ValueError(f'Unknown move: {move_id}')
    move['name']=name.strip()
    move['name_status']='descriptive_mod_name'
    if category is not None:
        if not isinstance(category,str) or not ID.fullmatch(category):
            raise ValueError('Category must be a lowercase identifier')
        move['category']=category
    save_catalogue(catalogue_path,data)
    return data


def merge_recording(catalogue_path, summary):
    # Import either one take or an interruption-separated encounter.
    # Resolve each segment beside its index and use the same merge logic.
    # Retries stay distinct while repeated imports remain idempotent.
    # For an index, segment `summary`/`summary_path`/`path` files are resolved next
    # to the index; each is independently merged, so interruptions stay separate.
    data=load_catalogue(catalogue_path)
    summary_path=Path(summary) if isinstance(summary,(str,Path)) else None
    record=json.loads(summary_path.read_text(encoding='utf-8')) if summary_path else summary
    if record.get('kind')=='encounter_reconstruction':
        data=merge_reconstruction(data,record,str(summary_path) if summary_path else None)
    else:
        if summary_path is None:
            raise ValueError('A segmented encounter index must be passed by path')
        segments=record.get('segments')
        if not isinstance(segments,list):
            raise ValueError('Expected encounter reconstruction or segment index')
        for segment in segments:
            relative=segment.get('summary') or segment.get('summary_path') or segment.get('path')
            if not relative:
                raise ValueError('Encounter segment has no summary path')
            source=Path(relative)
            if not source.is_absolute():
                source=summary_path.parent/source
            reconstructed=json.loads(source.read_text(encoding='utf-8'))
            data=merge_reconstruction(data,reconstructed,str(source))
    save_catalogue(catalogue_path,data)
    return data


def merge_unique_records(target, values):
    # Retain new evidence without repeating identical records.
    # Compare each bounded record and append a detached copy once.
    # Later edits to the reconstruction cannot mutate the catalogue.
    for value in values:
        if value not in target:
            target.append(copy.deepcopy(value))


def reconstruction_evidence(values):
    # Limit imported evidence to durable provenance fields.
    # Copy only paths, line numbers, times and descriptive metadata.
    # Runtime addresses cannot leak through arbitrary evidence objects.
    return [{k:e[k] for k in ('path','line','t','kind','detail','segment') if k in e} for e in values]


def merge_reconstruction(catalogue, reconstruction, evidence_path=None):
    # Merge observed actions without promoting gameplay readiness.
    # Deduplicate the reconstruction and match boss-local source identities.
    # Curated labels, bindings and confirmed follow-ups stay authoritative.
    # Human names/bindings/status remain authoritative. Reconstructed temporal
    # adjacency is added under combo.observed_successors, never confirmed_followups.
    result = copy.deepcopy(validate_catalogue(catalogue))
    if reconstruction.get('schema_version') != 1 or reconstruction.get('kind') != 'encounter_reconstruction':
        raise ValueError('Expected encounter_reconstruction schema version 1')
    boss_id = reconstruction['boss_id']
    if not ID.fullmatch(boss_id):
        raise ValueError('Invalid boss ID')
    curated = {m['source']['action_id']: m for m in iter_moves(result) if m['boss_id'] == boss_id and m['weapon'] == 'sword'}
    words = {m['source'].get('observed_word0_u16') for m in curated.values()}
    actions = [a for a in reconstruction.get('actions', []) if a.get('role') == 'boss_candidate'
               and (a.get('source', {}).get('action_id') in curated
                    or a.get('source', {}).get('action_id') is None
                    and a.get('source', {}).get('observed_word0_u16') is not None
                    and a['source']['observed_word0_u16'] in words)]
    if not actions:
        return result
    identities = {a.get('identity') or a.get('key') or a.get('id') for a in actions}
    identities.discard(None)
    fingerprint = hashlib.sha256(json.dumps(reconstruction,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if any(e.get('sha256') == fingerprint for e in result.setdefault('encounters',[])):
        return result
    source_hash=reconstruction.get('source',{}).get('sha256')
    previous=next((e for e in result['encounters'] if source_hash and e.get('source_sha256')==source_hash and e['boss_id']==boss_id),None)
    metadata_only=previous is not None
    # A better decoder enriches the same raw capture; it does not create new
    # sightings or encounters. Keep its original identity and update decoded facts.
    if previous is None:
        previous={'id':fingerprint[:16],'boss_id':boss_id,'path':evidence_path}
        result['encounters'].append(previous)
    previous.update(sha256=fingerprint,complete=bool(reconstruction.get('complete')),issues=reconstruction.get('issues',[]))
    if source_hash:
        previous['source_sha256']=source_hash
    for action in actions:
        source = action.get('source',{})
        action_id=source.get('action_id')
        word=source.get('observed_word0_u16')
        if action_id is None:
            # A low word alone must not be promoted to the known full ID. Keep
            # only ambiguity involving a retained sword identity, without importing
            # unrelated player states or repopulating discarded non-sword records.
            if not metadata_only:
                possible=[m['id'] for m in curated.values() if m['source'].get('observed_word0_u16')==word]
                result['observations'].append({'id':f'{boss_id}.word_sample_{fingerprint[:12]}_{word:04x}','boss_id':boss_id,'status':'word0_only','source':copy.deepcopy(source),'candidate_move_ids':possible,'evidence':reconstruction_evidence(action.get('evidence',[]))})
            continue
        move=curated[action_id]
        disagreements={field:{'catalogue':move['source'].get(field),'observed':source[field]} for field in ('motion_id','timing_id','timing_override') if source.get(field) is not None and move['source'].get(field) is not None and source[field]!=move['source'][field]}
        if disagreements:
            merge_unique_records(move.setdefault('source_conflicts',[]),[{'fields':disagreements,'evidence':reconstruction_evidence(action.get('evidence',[])),'status':'requires_classification'}])
        else:
            for field in ('motion_id','timing_id','timing_override'):
                if move['source'].get(field) is None and source.get(field) is not None:
                    move['source'][field]=source[field]
        if not metadata_only:
            merge_unique_records(move['evidence'],reconstruction_evidence(action.get('evidence',[])))
        for field in ('flags', 'ki_cost', 'recovery_frame', 'cancel_frame', 'transition_targets',
                      'ki_pulse_percent', 'ki_pulse_start', 'ki_pulse_fill', 'ki_pulse_hold',
                      'transition_links', 'combat_rows', 'transition_rows_total', 'transition_rows_omitted',
                      'combat_rows_total', 'combat_rows_omitted'):
            if not disagreements and field in source and field not in move['source']:
                move['source'][field] = copy.deepcopy(source[field])
        if not metadata_only:
            move['capture']['state_events'] = move['capture'].get('state_events', 0) + action['observations']
        if metadata_only:
            continue
        if evidence_path:
            merge_unique_records(move['evidence'],[{'path':evidence_path,'kind':'encounter_reconstruction','detail':'Observed sequences and state evidence, not verified combos.'}])
        identity = action.get('identity') or action.get('key') or action.get('id')
        for edge in reconstruction.get('observed_successors',[]):
            from_id=edge.get('from')
            target=edge.get('to')
            if not (target.get('action_id') in curated if isinstance(target,dict) else target in identities):
                continue
            source_match=isinstance(from_id,dict) and ((action_id is not None and from_id.get('action_id')==action_id) or (action_id is None and from_id.get('observed_word0_u16')==word))
            if edge.get('actor_label')==action.get('actor_label') and (source_match or (identity is not None and from_id==identity)):
                merge_unique_records(move['combo']['observed_successors'],[edge])
        if evidence_path:
            merge_unique_records(move['combo']['strings'],[{'path':evidence_path,'section':'strings','status':'observed_not_confirmed'}])
    return validate_catalogue(result)


def main():
    # Expose catalogue validation and reconstruction import for source tooling.
    # Read the selected catalogue, optionally merge evidence, then report counts.
    # The command edits metadata only and never starts a runtime.
    parser=argparse.ArgumentParser(description='Maintain boss moves and merge encounter discoveries.')
    parser.add_argument('--catalogue',type=Path,default=DEFAULT_PATH)
    parser.add_argument('--import-reconstruction',type=Path)
    args=parser.parse_args()
    data=load_catalogue(args.catalogue)
    if args.import_reconstruction:
        source=args.import_reconstruction
        record=json.loads(source.read_text(encoding='utf-8'))
        try: evidence_path=source.resolve().relative_to(DEFAULT_PATH.parent.parent).as_posix()
        except ValueError: evidence_path=source.name
        data=merge_reconstruction(data,record,evidence_path)
        save_catalogue(args.catalogue,data)
    print(json.dumps({'moves':len(data['moves']),'selectable':sum(m['implementation']['selectable'] for m in data['moves']),'observations':len(data['observations']),'encounters':len(data['encounters'])}))


if __name__=='__main__':
    main()
