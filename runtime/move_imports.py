import json
import sys
from pathlib import Path

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from catalogue import load_catalogue, iter_moves

# TODO: add adapters only after their native dependencies and gameplay behavior are verified.
SUPPORTED_SOURCE_FLAGS = 0x184C0000
GRAB_ATTEMPT_FLAGS = 0x594C0000
PAIRED_ATTACKER_FLAGS = 0x8078000000
PLAYER_REPLACEMENT_FLAGS = 0x194C0000
STANCE_SKILL_FLAGS = 0x200194C0000
PLAYER_PAIRED_FLAGS = 0x8038000000
IMPORT_LIMIT = 24
PLAYER_TEMPLATES = {0xCF5: (4300, 46, 38), 0xCF6: (4310, 46, 29), 0xCF7: (4320, 44, 33),
                    0xCB7: (3300, 40, 58), 0xC7A: (2300, 42, 46)}
STANCE_OPENERS = {'low': 0xCF5, 'mid': 0xCB7, 'high': 0xC7A}


def is_airborne_sword(move):
    # Admit the recorded Flying Swallow and somersault graphs.
    # Bound zero-flag airborne imports by exact source identity and adapter role.
    # Grounded sword adaptation is used only after the landing action begins.
    return (move.get('key'),move.get('motion'),move.get('flags'),move.get('adapter_kind')) in (
        (0xC71,1050,0,2),(0xC72,5000,0,4),(0xC73,5001,0,4),(0xC74,5002,0x1BCE0000,4),
        (0xC81,1050,0,2),(0xC82,5050,0,4),(0xC83,5051,0x1BCE0000,4))


def is_izuna_bridge(move):
    # Admit only the recorded airborne contact bridge, not an arbitrary zero-flag action.
    # Match its action, motion and continuation adapter together.
    # Its native condition22 remains the sole entry to the paired attacker.
    return (move.get('key'),move.get('motion'),move.get('flags'),move.get('adapter_kind')) == (0xC7A,1050,0,4)


def shared_launcher(first, second):
    # Keep low standalone C79 separate from the mid Izuna entry using the same source bytes.
    # Require distinct verified stance templates and identical source signatures/resources.
    # No other duplicate action key or third alias can enter one runtime table.
    fields=('key','motion','flags','ki_cost','recovery_frame','transition_count','source_payload_prefix',
            'source_voices','voices','descriptor','payload','clip','timing_record')
    return ({first['id'],second['id']} == {'jin_hayabusa.action_0c79','jin_hayabusa.izuna_drop'}
            and (first['key'],first['motion'],first['flags']) == (0xC79,5014,PLAYER_REPLACEMENT_FLAGS)
            and first.get('adapter_kind') == second.get('adapter_kind') == 2
            and all(first.get(field)==second.get(field) for field in fields)
            and first['replacement']['player_key'] in STANCE_OPENERS.values()
            and second['replacement']['player_key'] in STANCE_OPENERS.values()
            and first['replacement']['player_key'] != second['replacement']['player_key'])


def check_import_topology(moves, string_variant):
    # Reject import graphs the native adapter cannot safely execute.
    # Check source families, bounds, voice slots and successor cycles.
    # Only a grab-success edge may enter a paired attacker action.
    if not isinstance(moves, list) or not 2 <= len(moves) <= IMPORT_LIMIT:
        raise ValueError('Import table requires 2 to 24 moves')
    if any(not isinstance(move, dict) for move in moves):
        raise ValueError('Import rows must be objects')
    replacement_only = string_variant is None and all(move['flags'] in (PLAYER_REPLACEMENT_FLAGS, STANCE_SKILL_FLAGS, PLAYER_PAIRED_FLAGS) or is_izuna_bridge(move) or is_airborne_sword(move) for move in moves)
    if not replacement_only and (type(string_variant) is not int or not 0 <= string_variant < len(moves)):
        raise ValueError('String entry is outside the import table')
    ids, keys = set(), {}
    for move in moves:
        for field in ('id', 'name'):
            if not isinstance(move[field], str) or not move[field].strip():
                raise ValueError('Import IDs and names must be nonempty strings')
        if move['id'] in ids or move['key'] in keys and not shared_launcher(keys[move['key']],move):
            raise ValueError('Duplicate move ID or action key')
        ids.add(move['id']); keys[move['key']]=move
        flags = move['flags']
        bridge=is_izuna_bridge(move)
        airborne=is_airborne_sword(move)
        replacement = flags in (PLAYER_REPLACEMENT_FLAGS, STANCE_SKILL_FLAGS) or bridge or airborne
        if replacement and (move['adapter_kind'] not in (1, 2, 4)
                or flags == STANCE_SKILL_FLAGS and move['adapter_kind'] not in (2, 4)):
            raise ValueError('Source action family requires a supported native adapter')
        for field, lower, upper in (('key', 1, 0xfffe), ('motion', 0, 0x7fffffff),
                ('recovery_frame', -1, 0x7fff), ('transition_count', 1, 128 if replacement else 28), ('ki_cost', 0, 0x7fff),
                ('next_variant', -1, len(moves)-1), ('next_start', 0, 0x7fff), ('next_end', 0, 0x7fff)):
            if type(move[field]) is not int or not lower <= move[field] <= upper:
                raise ValueError(f'Import {field} is outside supported bounds')
        if type(flags) is not int or not (bridge or airborne) and flags not in (SUPPORTED_SOURCE_FLAGS, GRAB_ATTEMPT_FLAGS, PAIRED_ATTACKER_FLAGS, PLAYER_REPLACEMENT_FLAGS, STANCE_SKILL_FLAGS, PLAYER_PAIRED_FLAGS):
            raise ValueError('Unsupported source action family')
        if bridge and (move['recovery_frame'],move['ki_cost'],move['transition_count']) != (-1,0,19):
            raise ValueError('Izuna contact bridge differs from its recorded source')
        if airborne and (move['recovery_frame'],move['ki_cost'],move['transition_count'],move['next_variant']) != {
                0xC71:(-1,0,18,-1),0xC72:(-1,20,17,-1),0xC73:(-1,0,18,-1),0xC74:(20,0,75,-1),
                0xC81:(-1,0,18,-1),0xC82:(-1,10,18,-1),0xC83:(-1,0,75,-1)}[move['key']]:
            raise ValueError('Airborne sword move differs from its recorded native graph')
        if ((flags == SUPPORTED_SOURCE_FLAGS or replacement and move['adapter_kind'] == 1) and move['recovery_frame'] <= 0
                or flags in (GRAB_ATTEMPT_FLAGS, PAIRED_ATTACKER_FLAGS, PLAYER_PAIRED_FLAGS) and move['recovery_frame'] != -1):
            raise ValueError('Recovery policy differs from the source action family')
        if replacement and move['next_variant'] != -1 and (move['adapter_kind'] != 2 and not bridge or move['next_start'] or move['next_end']):
            raise ValueError('Player replacement follows native player transitions, not a timed source chain')
        if move['next_variant'] == -1:
            if move['next_start'] or move['next_end']:
                raise ValueError('Terminal move cannot have a combo window')
        elif flags == GRAB_ATTEMPT_FLAGS or replacement:
            if move['next_start'] or move['next_end']:
                raise ValueError('Paired success is a native transition, never a timed link')
        elif flags in (PAIRED_ATTACKER_FLAGS, PLAYER_PAIRED_FLAGS) or move['next_start'] > move['next_end'] or not move['next_end']:
            raise ValueError('Invalid combo window')
        voices = move['voices']
        if not isinstance(voices, list) or len(voices) > 3:
            raise ValueError('An import supports at most three voice events')
        positions = set()
        for voice in voices:
            for field, lower, upper in (('frame', 0, 0xffff), ('index', 0, 511), ('hash', 1, 0xffffffff)):
                if type(voice[field]) is not int or not lower <= voice[field] <= upper:
                    raise ValueError(f'Import voice {field} is outside supported bounds')
            position = voice['frame'], voice['index']
            if position in positions:
                raise ValueError('Duplicate voice event')
            positions.add(position)
    for move in moves:
        if move['next_variant'] != -1:
            target = moves[move['next_variant']]
            if move['flags'] in (PLAYER_REPLACEMENT_FLAGS, STANCE_SKILL_FLAGS) or is_izuna_bridge(move):
                if target['flags'] != PLAYER_PAIRED_FLAGS:
                    raise ValueError('Hold contact must enter a native paired source action')
                if is_izuna_bridge(move) and (target['key'],target['motion'],target.get('adapter_kind')) != (0x3B2,5020,3):
                    raise ValueError('Izuna contact must enter the recorded paired lift')
            elif target['flags'] == PLAYER_PAIRED_FLAGS or ((move['flags'] == GRAB_ATTEMPT_FLAGS) != (target['flags'] == PAIRED_ATTACKER_FLAGS)):
                raise ValueError('Only the native grab-success link may enter a paired action')
    if not replacement_only and (moves[string_variant]['flags'] in (PAIRED_ATTACKER_FLAGS, PLAYER_REPLACEMENT_FLAGS, STANCE_SKILL_FLAGS, PLAYER_PAIRED_FLAGS) or is_izuna_bridge(moves[string_variant]) or is_airborne_sword(moves[string_variant])):
        raise ValueError('A paired or player-replacement action cannot be the direct string entry')
    for start in range(len(moves)):
        visited = set()
        current = start
        while current != -1:
            if current in visited:
                raise ValueError('Import combo topology contains a cycle')
            visited.add(current)
            current = moves[current]['next_variant']


def read_import_manifest(path, catalogue_path=None):
    # Resolve named configured successors into runtime table indices.
    # Validate the manifest's source profile and preserve baseline slots zero/one.
    # Adding supported ordinary actions stays configuration work.
    manifest = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if manifest['schema_version'] != 1 or type(manifest['schema_version']) is not int:
        raise ValueError('Unsupported import manifest version')
    if (manifest['boss_id'], manifest['resource_profile_id']) not in (
            ('okatsu', 'okatsu.resources.v1'), ('jin_hayabusa', 'jin_hayabusa.resources.v1')):
        raise ValueError('Import manifest does not match the owned resource profile')
    moves = manifest['moves']
    if not isinstance(moves, list) or not 2 <= len(moves) <= IMPORT_LIMIT:
        raise ValueError('Import table requires 2 to 24 moves')
    positions = {move['id']: index for index, move in enumerate(moves)}
    if manifest['string_entry'] is not None and manifest['string_entry'] not in positions:
        raise ValueError('Unknown string entry move')
    for move in moves:
        move.setdefault('name', move['id'])
        target = move.pop('next')
        if target is not None and target not in positions:
            raise ValueError('Unknown combo target move')
        move['next_variant'] = -1 if target is None else positions[target]
    manifest['string_variant'] = positions[manifest['string_entry']] if manifest['string_entry'] is not None else None
    check_import_topology(moves, manifest['string_variant'])
    if manifest['boss_id'] == 'okatsu' and [(move['key'], move['motion']) for move in moves[:2]] != [(0xC64, 1220), (0xC66, 1230)]:
        raise ValueError('Import slots 0 and 1 must preserve the Okatsu baseline')
    if manifest['boss_id'] == 'jin_hayabusa':
        for move in moves:
            if move['adapter_kind'] == 3:
                if move['flags'] != PLAYER_PAIRED_FLAGS or 'replacement' in move:
                    raise ValueError('Paired source adapter cannot replace a player descriptor')
                continue
            adapter = move['replacement']
            values = tuple(adapter[field] for field in ('player_motion', 'transition_count', 'recovery_frame'))
            if (move['adapter_kind'] not in (1, 2, 4) or not (move['flags'] in (PLAYER_REPLACEMENT_FLAGS, STANCE_SKILL_FLAGS) or is_izuna_bridge(move) or is_airborne_sword(move)) or type(adapter['player_key']) is not int
                    or is_airborne_sword(move) and adapter['player_key']!=(0xCF5 if move['key']<0xC81 else 0xC7A)
                    or adapter['player_key'] not in PLAYER_TEMPLATES or values != PLAYER_TEMPLATES[adapter['player_key']]
                    or move['adapter_kind'] == 1 and adapter['player_key'] not in (0xCF5, 0xCF6, 0xCF7)
                    or move['adapter_kind'] in (2, 4) and adapter['player_key'] not in STANCE_OPENERS.values()
                    or any(type(value) is not int for value in values)):
                raise ValueError('Unverified player replacement signature')
    catalogue = load_catalogue(catalogue_path) if catalogue_path is not None else load_catalogue()
    names = {move['id']: move['name'] for move in iter_moves(catalogue)}
    for move in moves:
        move['name'] = names[move['id']]
    return manifest
