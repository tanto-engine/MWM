# Portable movesets. Stable move identifiers, never process addresses.
import copy
import json
import math
import os
from pathlib import Path
import tempfile
import time

if os.name == 'nt':
    import ctypes as C
    from ctypes import wintypes as W
    import msvcrt
    kernel = C.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [W.LPCWSTR, W.DWORD, W.DWORD, C.c_void_p, W.DWORD, W.DWORD, W.HANDLE]
    kernel.CreateFileW.restype = W.HANDLE
    kernel.CloseHandle.argtypes = [W.HANDLE]
    kernel.ReplaceFileW.argtypes = [W.LPCWSTR, W.LPCWSTR, W.LPCWSTR, W.DWORD, C.c_void_p, C.c_void_p]
    kernel.ReplaceFileW.restype = W.BOOL

# Native signatures and resource indices belong to imports, saved device masks to calibration.
# Preset validation does not certify gameplay acceptance.
from engine_policy import NATIVE_SKILLS
from gestures import SEQUENCE_WINDOW_SECONDS
from move_imports import BINDING_LIMIT
from project_paths import DATA

# Product manifests own the choices; native preparation still verifies every source signature.
_ordinary = json.loads((DATA/'imports/okatsu.json').read_text(encoding='utf8'))
_sword = json.loads((DATA/'imports/jin_hayabusa.json').read_text(encoding='utf8'))
_trials = [json.loads(path.read_text(encoding='utf8')) for path in sorted((DATA/'imports').glob('*.json'))
           if path.stem not in ('okatsu','jin_hayabusa')]
SOURCE_MANIFESTS = [_sword, *_trials]
MOVE_VARIANTS = {move['id']: i for i, move in enumerate(_ordinary['moves'][:2] +
    [move for move in _sword['moves'] if move['adapter_kind']==5])}
HEAVY_STRINGS = {chain[0]: name for name, chain in _sword['candidates'].items()}
HELD_MOVES = frozenset(root for source in SOURCE_MANIFESTS for root in source['hold_chains']) | frozenset(HEAVY_STRINGS)
HELD_INPUT_MOVES = HELD_MOVES | frozenset(move['id'] for move in _ordinary['moves'][:2])
CHORD_MOVES = frozenset(MOVE_VARIANTS) | HELD_MOVES
SPEED_MOVES = frozenset(move['id'] for move in _ordinary['moves'] + [m for source in SOURCE_MANIFESTS for m in source['moves']]
    if move['flags'] not in (0x8078000000, 0x8038000000))
CUSTOM_BINDING_LIMIT = 24
PRESET_FIELDS = frozenset('schema_version name weapon tap_move hold_move modifier_mask trigger_mask hold_seconds low_heavy stance_holds okatsu_grapple mid_light_ender string_enabled skill_bindings frost_moon chord_stance move_settings'.split())
SOURCE_LABELS = dict(tiger_sprint='Tiger Sprint',dodge_attack='Dodge attack',heavy_attack='Heavy attack',
    guard_light='Guard + light attack',light_attack='Quick attack',high_heavy_followup='High-heavy follow-up')
MOVE_HELP = json.loads((DATA/'move-help.json').read_text(encoding='utf8'))


def move_label(identifier):
    # Name validation conflicts using the same catalogue labels shown in the move menu.
    # Look up labels only when needed so ordinary validation does not reread the catalogue.
    # Unknown file values retain their identifier instead of being mistaken for a supported move.
    from catalogue import load_catalogue, iter_moves
    return next((move['name'] for move in iter_moves(load_catalogue()) if move['id']==identifier),str(identifier))


def move_capabilities():
    # Tell the trainer which reviewed moves can actually be configured.
    # Join readable catalogue names to implemented imports and their supported binding/speed roles.
    # A raw recording or catalogue entry alone never becomes a playable menu choice.
    from catalogue import load_catalogue, iter_moves
    names = {move['id']: move['name'] for move in iter_moves(load_catalogue())}
    ids = dict.fromkeys(move['id'] for move in _ordinary['moves'] + [m for source in SOURCE_MANIFESTS for m in source['moves']])
    return dict(moves=[dict(id=identifier, name=names[identifier], **MOVE_HELP['moves'][identifier], chord=identifier in CHORD_MOVES,
        graph=identifier in HELD_MOVES, held=identifier in HELD_INPUT_MOVES, heavy_string=identifier in HEAVY_STRINGS,
        native=identifier in CHORD_MOVES or identifier=='jin_hayabusa.action_0c6f',
        speed=identifier in SPEED_MOVES) for identifier in ids],
        native_sources=[dict(id=source, label=SOURCE_LABELS[source], **MOVE_HELP['sources'][source],
                             stances=['high'] if source=='high_heavy_followup' else ['low','mid','high','any'])
                        for source in (*NATIVE_SKILLS,'guard_light','light_attack','high_heavy_followup')],
        speed=dict(min=.25,max=2.0), stances=['low','mid','high'],chord_stances=['low','mid','high','any'],
        native_binding_limit=BINDING_LIMIT, custom_binding_limit=CUSTOM_BINDING_LIMIT,
        custom_sequence=dict(modifiers=['L1 / LB','Circle / B','Triangle / Y','L2 / LT','Square / X'],
                             buttons=['L1 / LB','Circle / B','Triangle / Y','L2 / LT','Square / X'],
                             window_seconds=SEQUENCE_WINDOW_SECONDS))


def atomic_json(path, value):
    # Publish runtime state while Windows readers hold shared handles.
    # Serialize to a sibling file and use bounded atomic replacement.
    # Sharing races are retried; unrelated write failures remain visible.
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf8', dir=path.parent,
                                         prefix=path.name+'.', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, indent=2, allow_nan=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        # ReplaceFileW can replace a destination held by share-delete readers;
        # MoveFileEx (Path.replace) rejects that overlap on Windows. Legacy
        # readers without delete sharing get a short, bounded retry.
        for attempt in range(6):
            try:
                if os.name == 'nt':
                    if not kernel.ReplaceFileW(str(path), str(temporary), None, 0, None, None):
                        error = C.get_last_error()
                        if error != 2:  # A new destination has no file to replace.
                            raise C.WinError(error)
                        temporary.replace(path)
                else:
                    temporary.replace(path)
                break
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(.005)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def read_json(path, default=None):
    # Read state files without blocking an atomic Windows replacement.
    # Open with delete sharing and bound retries for transient name/lock gaps.
    # Only genuine absence returns the caller's explicit default.
    try:
        if os.name == 'nt':
            # Atomic replacement requires delete sharing in both directions:
            # readers must coexist with the writer's temporary DELETE handle.
            for attempt in range(6):
                handle = kernel.CreateFileW(str(Path(path)), 0x80000000, 7, None, 3, 0x80, None)
                if handle != C.c_void_p(-1).value:
                    break
                error = C.get_last_error()
                # Replacement briefly locks the new file and can leave a name
                # gap. Genuine absence still returns the caller's default after
                # this bounded window; access denials are never retried.
                if error not in (2, 32) or attempt == 5:
                    raise C.WinError(error)
                time.sleep(.005)
            try:
                descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY)
            except OSError:
                kernel.CloseHandle(handle)
                raise
            with os.fdopen(descriptor, 'r', encoding='utf-8-sig') as stream:
                return json.load(stream)
        return json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except FileNotFoundError:
        return copy.deepcopy(default)


def validate_preset(value):
    # Reject movesets the current runtime cannot execute.
    # Check schema, implemented move IDs, distinct button bits and hold time.
    # Corrupt settings cannot silently become a different binding.
    if isinstance(value,dict) and type(value.get('schema_version')) is int and value['schema_version'] in (4,5,6,7):
        value={key:item for key,item in value.items() if key not in ('launch_profiles','air_juggle_boost','tracking_rates','izuna_tracking_degrees','frost_window_seconds','frost_startup_speed')}
        value=dict(value,schema_version=8)
        value.setdefault('chord_stance','low')
        value.setdefault('move_settings',{})
    if not isinstance(value, dict) or type(value.get('schema_version')) is not int or value['schema_version'] != 8:
        raise ValueError('Unsupported moveset version')
    missing = [key for key in PRESET_FIELDS if key not in value]
    if missing:
        raise ValueError('Incomplete moveset: missing ' + ', '.join(missing))
    if set(value) != PRESET_FIELDS:
        raise ValueError('Unknown preset fields: ' + ', '.join(sorted(set(value)-PRESET_FIELDS)))
    result = copy.deepcopy(value)
    if not isinstance(result['name'], str) or not result['name'].strip() or len(result['name']) > 100:
        raise ValueError('Give the moveset a name of 1 to 100 characters')
    for key in ('tap_move', 'hold_move'):
        if result[key] is not None and (not isinstance(result[key], str) or result[key] not in CHORD_MOVES):
            raise ValueError(f'Custom chord {key.split("_")[0]}: {move_label(result[key])} cannot be assigned here. Choose a move from this control’s menu.')
    if result['chord_stance'] not in ('low','mid','high','any'):
        raise ValueError('Choose a stance or Any for the custom chord')
    settings=result['move_settings']
    if not isinstance(settings,dict): raise ValueError('Move settings must map move IDs to speed')
    for identifier, fields in settings.items():
        if identifier not in SPEED_MOVES or not isinstance(fields,dict) or set(fields)!={'speed'}:
            raise ValueError(f'{move_label(identifier)}: only speed for supported unpaired moves can be edited. Remove this unsupported setting.')
        speed=fields['speed']
        if type(speed) not in (int,float) or not math.isfinite(speed) or not .25<=speed<=2:
            raise ValueError(f'{move_label(identifier)}: move speed must be between 0.25 and 2. Enter a number within that range.')
    for key in ('modifier_mask', 'trigger_mask'):
        bit = result[key]
        if not isinstance(bit, int) or isinstance(bit, bool) or not 0 < bit <= 0x80000000 or bit & (bit-1):
            raise ValueError(f'Custom chord {key.split("_")[0]} requires one controller button. Choose a single supported input for this field.')
    if result['modifier_mask'] == result['trigger_mask']:
        raise ValueError('Custom chord modifier and trigger use the same button. Choose two different buttons.')
    seconds = result['hold_seconds']
    if isinstance(seconds, bool) or not isinstance(seconds, (float, int)) or not math.isfinite(seconds) or not .08 <= seconds <= 2:
        raise ValueError('Hold threshold must be between 0.08 and 2 seconds')
    if result['weapon'] != 'sword' or result['low_heavy'] not in (None, *HEAVY_STRINGS):
        raise ValueError('Choose a supported sword string for low Triangle')
    holds=result['stance_holds']
    if not isinstance(holds, dict) or set(holds) != {'low','mid','high'}:
        raise ValueError('Held Triangle requires low, mid and high entries')
    enabled=[move for move in holds.values() if move is not None]
    if any(not isinstance(move,str) or move not in HELD_INPUT_MOVES for move in enabled):
        move=next(move for move in enabled if not isinstance(move,str) or move not in HELD_INPUT_MOVES)
        raise ValueError(f'{move_label(move)} cannot be assigned to hold Triangle / Y. Choose a move from the held-input menu.')
    frost=result['frost_moon']
    if not isinstance(frost,dict) or set(frost)!=set(holds):
        raise ValueError('Frost Moon requires low, mid and high entries')
    if any(identifier is not None and (not isinstance(identifier,str) or identifier not in CHORD_MOVES) for identifier in frost.values()):
        stance,move=next((stance,move) for stance,move in frost.items() if move is not None and (not isinstance(move,str) or move not in CHORD_MOVES))
        raise ValueError(f'{move_label(move)} cannot be assigned to {stance.title()} Frost Moon. Choose a move from the Frost Moon menu.')
    bindings=result['skill_bindings']
    if not isinstance(bindings,list):
        raise ValueError('Native overrides must contain source, stance and move rows. Reload a valid moveset.')
    entries=[(stance,move,f'{stance.title()} {label}') for mapping,label in ((holds,'hold Triangle / Y'),(frost,'Frost Moon'))
             for stance,move in mapping.items() if move and (move in HELD_MOVES or move in frost.values())]
    entries += [(result['chord_stance'],result[field],f'Custom chord {field.split("_")[0]} ({result["chord_stance"].title()})') for field in ('tap_move','hold_move')
                if result[field] in HELD_MOVES or result[field] is not None and result[field] in frost.values()]
    if result['chord_stance']=='any' and any(result[field] in HELD_MOVES for field in ('tap_move','hold_move')):
        move=next(result[field] for field in ('tap_move','hold_move') if result[field] in HELD_MOVES)
        raise ValueError(f'Choose Low, Mid or High for the custom chord: {move_label(move)} needs one stance for its move sequence. Any stance is not supported for this move.')
    occupied={}
    routes=[]
    for gesture,field in (('tap','tap_move'),('hold','hold_move')):
        if result[field] is not None:
            routes.append((result['chord_stance'],result['modifier_mask'],result['trigger_mask'],None,gesture))
    custom_count=0
    for binding in bindings:
        if not isinstance(binding,dict) or set(binding) not in ({'source','stance','move'}, {'source','stance','move','input'}):
            raise ValueError('Skill binding requires source, stance and move')
        source,stance,move=(binding[field] for field in ('source','stance','move'))
        if source not in (*NATIVE_SKILLS,'guard_light','light_attack','high_heavy_followup') or stance not in (*holds,'any') or move not in (*HELD_MOVES,*MOVE_VARIANTS,'jin_hayabusa.action_0c6f'):
            label=SOURCE_LABELS.get(source,source) if isinstance(source,str) else str(source)
            raise ValueError(f'Unsupported skill binding: {label} ({stance}) → {move_label(move)}. Choose a source, stance and move from the supported menus.')
        custom=binding.get('input')
        if custom is not None:
            sequence=isinstance(custom,dict) and custom.get('gesture')=='sequence'
            required={'modifier_mask','trigger_mask','followup_mask','gesture'} if sequence else {'modifier_mask','trigger_mask','gesture'}
            if not isinstance(custom,dict) or set(custom)!=required:
                raise ValueError('Custom input requires modifier_mask, trigger_mask, gesture and followup_mask for a sequence')
            modifier,trigger,gesture=(custom[key] for key in ('modifier_mask','trigger_mask','gesture'))
            followup=custom['followup_mask'] if sequence else None
            bits=(modifier,trigger,followup) if sequence else (modifier,trigger)
            if (any(type(bit) is not int or not 0<bit<=0x80000000 or bit&(bit-1) for bit in bits)
                    or len(set(bits))!=len(bits) or gesture not in ('tap','hold','sequence')):
                raise ValueError('Custom input requires distinct single button bits and tap, hold or sequence')
            if move not in CHORD_MOVES:
                raise ValueError(f'{move_label(move)} cannot use a custom input; choose its original source')
            if stance=='any' and move in HELD_MOVES:
                raise ValueError(f'{move_label(move)} needs one stance for its move sequence')
            for old_stance,old_modifier,old_trigger,old_followup,old_gesture in routes:
                overlap=stance=='any' or old_stance=='any' or stance==old_stance
                if overlap and (sequence or old_gesture=='sequence') and {modifier,trigger}=={old_modifier,old_trigger}:
                    raise ValueError('A sequence start overlaps another custom input in this stance; choose different buttons')
                if overlap and not sequence and old_gesture!='sequence' and {modifier,trigger}=={old_modifier,old_trigger} and (modifier,trigger)!=(old_modifier,old_trigger):
                    raise ValueError('The reversed custom chord overlaps another route in this stance; choose different buttons')
                if overlap and (modifier,trigger,followup,gesture)==(old_modifier,old_trigger,old_followup,old_gesture):
                    raise ValueError('This custom chord gesture already selects a move in this stance')
            routes.append((stance,modifier,trigger,followup,gesture))
            custom_count+=1
        if move=='jin_hayabusa.action_0c6f' and (source!='dodge_attack' or stance!='low' or result['low_heavy']!='jin_hayabusa.action_0c6e'):
            raise ValueError(f'{move_label(move)} requires Low Dodge attack and the {move_label("jin_hayabusa.action_0c6e")} Low Triangle / Y string. Enable that string and choose Low Dodge attack, or choose another move.')
        if move in HELD_MOVES and stance=='any':
            raise ValueError(f'{SOURCE_LABELS[source]}: {move_label(move)} needs one stance for its move sequence. Choose Low, Mid or High instead of Any.')
        if custom is None and source=='high_heavy_followup' and stance!='high':
            raise ValueError(f'High-heavy follow-up for {move_label(move)} requires High stance because it follows the High heavy attack. Choose High or another source.')
        if custom is None:
            scopes=list(holds) if stance=='any' else [stance]
            for scope in scopes:
                if (source,scope) in occupied:
                    raise ValueError(f'{scope.title()} {SOURCE_LABELS[source]} selects both {move_label(occupied[source,scope])} and {move_label(move)}. Only one override can own this input; remove one row or change its source or stance.')
                occupied[source,scope]=move
        if move in HELD_MOVES or move in frost.values(): entries.append((stance,move,f'{stance.title()} {"custom input" if custom else SOURCE_LABELS[source]}'))
    if custom_count>CUSTOM_BINDING_LIMIT:
        raise ValueError(f'Only {CUSTOM_BINDING_LIMIT} custom input rows are supported')
    owners={}
    for stance,move,label in entries:
        if move in owners and owners[move][0]!=stance:
            raise ValueError(f'{move_label(move)} is assigned to {owners[move][1]} and {label}. This move must use the same stance across bindings. To use {label}, clear {owners[move][1]} or choose a different move there.')
        owners[move]=(stance,label)
    launcher,drop=(owners.get(move) for move in ('jin_hayabusa.action_0c79','jin_hayabusa.izuna_drop'))
    if launcher and drop and launcher[0]==drop[0]:
        raise ValueError(f'{move_label("jin_hayabusa.action_0c79")} ({launcher[1]}) and {move_label("jin_hayabusa.izuna_drop")} ({drop[1]}) share a source action and require different stances. Move one assignment to another stance or disable it.')
    if result['low_heavy'] in owners:
        raise ValueError(f'{move_label(result["low_heavy"])} is used by the Low Triangle / Y string and {owners[result["low_heavy"]][1]}. The string cannot share its move sequence with another binding. Disable the Low Triangle / Y string or choose another move for that binding.')
    count=sum(3 if binding['source']=='heavy_attack' and binding['stance']=='any' else 1 for binding in bindings if 'input' not in binding)+len(enabled)
    if count>BINDING_LIMIT:
        raise ValueError(f'This setup uses {count} native override slots; only {BINDING_LIMIT} are supported. Held Triangle / Y uses one slot per stance; Heavy attack in Any stance uses three. Remove an override or held binding, or narrow an Any Heavy attack to one stance.')
    if any(type(result[key]) is not bool for key in ('okatsu_grapple','mid_light_ender','string_enabled')):
        raise ValueError('Grapple and string enable flags must be boolean')
    return result


DEFAULT_PRESET = validate_preset(json.loads((DATA/'preset.json').read_text(encoding='utf8')))


def binding_for_preset(calibration, preset, imports=None):
    # Combine a portable moveset with the saved device mapping.
    # Validate the preset and translate stable move IDs into runtime variants.
    # Session addresses never become part of a saved moveset.
    preset = validate_preset(preset)
    variants={move['id']:i for i,move in enumerate(imports)} if imports is not None else MOVE_VARIANTS
    if imports is not None and any(binding['move'] not in variants for binding in preset['skill_bindings'] if 'input' in binding):
        raise ValueError('Custom input move is absent from prepared imports')
    routes=[dict(**binding['input'],stance=binding['stance'],variant=variants.get(binding['move']))
            for binding in preset['skill_bindings'] if 'input' in binding]
    return dict(schema=1, device=copy.deepcopy(calibration['device']),
                  lb_mask=calibration['lb_mask'], circle_mask=preset['trigger_mask'],
                  modifier_mask=preset['modifier_mask'], trigger_mask=preset['trigger_mask'],
                  hold_seconds=preset['hold_seconds'], moveset=preset,
                  string_enabled=preset['string_enabled'],
                  variants=[variants.get(preset['tap_move']), variants.get(preset['hold_move'])], routes=routes)
