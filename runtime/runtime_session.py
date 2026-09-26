# Stable runtime startup ABI. A move identity never contains these pointers.
import re
import struct
from engine_policy import NATIVE_SKILLS, LAUNCH_PROFILES, TRACKING_RATES, AIR_JUGGLE_BOOST, validate_launch_profiles, validate_tracking_rates
from move_imports import check_import_topology, is_izuna_bridge, is_airborne_sword, IMPORT_LIMIT, PLAYER_REPLACEMENT_FLAGS, PLAYER_PAIRED_FLAGS, PLAYER_TEMPLATES, STANCE_OPENERS

POINTER_FIELDS = (
    'player', 'player_owner', 'source_action_resource', 'source_timing_resource', 'vtable',
    'source_bank', 'source_descriptor', 'source_payload', 'source_motion_bank', 'source_timing_wrapper', 'source_clip',
    'source_timing_record', 'player_motion', 'player_timing', 'charge_descriptor',
    'charge_payload', 'charge_clip', 'charge_timing_record', 'player_pulse_descriptor',
    'source_camera_bank', 'player_camera_slot', 'camera_original',
)
MOVE_IMPORT = struct.Struct('<5QIi hHhHHH 9I')
MOVE_ADAPTER = struct.Struct('<6QIiHhI')
ADAPTER_POINTERS = ('action_resource', 'timing_resource', 'bank', 'motion_bank', 'timing_wrapper', 'player_descriptor')
SESSION_CONFIG = struct.Struct('<4I12Q26Q2I' + '5QIi hHhHHH 9I' * IMPORT_LIMIT + '6QIiHhI' * IMPORT_LIMIT + '4IiIQ'*8 + 'IffI'*2 + '4f')
MAGIC, VERSION = 0x3153454e, 10
assert MOVE_IMPORT.size == 96 and MOVE_ADAPTER.size == 64 and SESSION_CONFIG.size == 5752


def encode_session(config, pid, creation_filetime):
    # Encode one validated runtime generation into the native ABI.
    # Check process identity, pointer fields, import topology and baseline records.
    # Only the original camera slot may be null; unused import slots are zeroed.
    identity = config['session']
    if (type(identity['pid']) is not int or identity['pid'] != pid
            or str(identity['creation_filetime']) != str(creation_filetime)):
        raise ValueError('Runtime session process identity differs from loader target')
    if not 0 < pid <= 0xffffffff or not 0 < int(creation_filetime) < 2 ** 64:
        raise ValueError('Invalid runtime process identity')
    tag = config['config_tag']
    if not isinstance(tag, str) or not re.fullmatch('[0-9a-f]{16}', tag) or not int(tag, 16):
        raise ValueError('Runtime session requires a nonzero 16-character config tag')
    originals = config['originals']
    if not isinstance(originals, list) or len(originals) != 4:
        raise ValueError('Runtime session requires four original resource slots')
    pointers = [config[name] for name in POINTER_FIELDS] + originals
    camera_original = POINTER_FIELDS.index('camera_original')
    if any(type(value) is not int or not (0x10000 <= value <= 0x7fffffffffff
            or index == camera_original and value == 0) for index,value in enumerate(pointers)):
        raise ValueError('Runtime session contains an absent or invalid user pointer')
    moves, string_variant = config['imports'], config['string_variant']
    check_import_topology(moves, string_variant)
    adapters = config['adapters']
    if not isinstance(adapters, list) or len(adapters) != len(moves):
        raise ValueError('Every import requires an explicit adapter slot')
    imports, encoded_adapters, player_keys = [], [], set()
    for index, move in enumerate(moves):
        addresses = [move[field] for field in ('descriptor', 'payload', 'clip', 'timing_record')]
        if any(type(value) is not int or not 0x10000 <= value <= 0x7fffffffffff for value in addresses):
            raise ValueError('Import contains an absent or invalid user pointer')
        if index < 2:
            prefix = 'source' if index == 0 else 'charge'
            expected = [config[prefix + '_' + field] for field in ('descriptor', 'payload', 'clip', 'timing_record')]
            if (addresses != expected or move['flags'] != 0x184C0000
                    or (move['key'], move['motion']) != ((0xC64, 1220), (0xC66, 1230))[index]):
                raise ValueError('Import baseline disagrees with legacy session fields')
        voices = [voice[field] for voice in move['voices'] for field in ('frame', 'index', 'hash')]
        imports.extend([*addresses, move['flags'], move['key'], move['motion'], move['recovery_frame'], move['transition_count'],
                        move['next_variant'], move['next_start'], move['next_end'], len(move['voices']),
                        *voices, *([0] * (9-len(voices)))])
        adapter = adapters[index]
        if adapter is None:
            if move['flags'] in (PLAYER_REPLACEMENT_FLAGS, PLAYER_PAIRED_FLAGS) or is_izuna_bridge(move) or is_airborne_sword(move):
                raise ValueError('Player replacement is missing its native adapter')
            encoded_adapters.extend([0] * 11)
            continue
        if not isinstance(adapter, dict) or index < 2:
            raise ValueError('Only the researched source family supports player replacement')
        kind = adapter['kind']
        if type(kind) is not int or kind not in (1, 2, 3, 4, 5) or kind != move['adapter_kind']:
            raise ValueError('Invalid or mismatched native adapter kind')
        replacement_pointers = [adapter[field] for field in ADAPTER_POINTERS]
        if any(type(value) is not int or not (0x10000 <= value <= 0x7fffffffffff
                or kind in (3,5) and field == 'player_descriptor' and value == 0)
                for field,value in zip(ADAPTER_POINTERS,replacement_pointers)):
            raise ValueError('Player replacement contains an invalid ownership pointer')
        fields = [adapter[field] for field in ('player_key', 'player_motion', 'transition_count', 'recovery_frame')]
        if kind in (3,5):
            if (kind==3 and move['flags']!=PLAYER_PAIRED_FLAGS or kind==5 and not is_airborne_sword(move)) or replacement_pointers[-1] or any(type(value) is not int or value for value in fields):
                raise ValueError('Paired adapter cannot supply player descriptor fields')
            encoded_adapters.extend([*replacement_pointers, *fields, kind])
            continue
        expected = PLAYER_TEMPLATES
        if (move['flags'] != PLAYER_REPLACEMENT_FLAGS and not (is_izuna_bridge(move) or is_airborne_sword(move)) or any(type(value) is not int for value in fields) or fields[0] not in expected
                or tuple(fields[1:]) != expected[fields[0]] or kind == 1 and fields[0] in player_keys
                or kind == 1 and fields[0] not in (0xCF5, 0xCF6, 0xCF7)
                or kind in (2, 4) and fields[0] not in STANCE_OPENERS.values()):
            raise ValueError('Player replacement signature is unsupported or duplicated')
        if fields != [move['replacement'][field] for field in ('player_key', 'player_motion', 'transition_count', 'recovery_frame')]:
            raise ValueError('Player replacement differs from the selected manifest mapping')
        if kind == 1:
            player_keys.add(fields[0])
        encoded_adapters.extend([*replacement_pointers, *fields, kind])
    hold_variant, hold_milliseconds, hold_camera = (config[field] for field in ('hold_variant','hold_milliseconds','hold_camera_bank'))
    if any(type(value) is not int for value in (hold_variant,hold_milliseconds,hold_camera)):
        raise ValueError('Hold configuration requires integer ABI fields')
    hold_slots = [index+1 for index,adapter in enumerate(adapters) if adapter is not None and adapter['kind'] == 2]
    paired_slots = [index for index,adapter in enumerate(adapters) if adapter is not None and adapter['kind'] == 3]
    if hold_variant:
        if (hold_variant not in hold_slots
                or not 80 <= hold_milliseconds <= 2000
                or not (hold_camera==0 and not paired_slots or 0x10000 <= hold_camera <= 0x7fffffffffff)):
            raise ValueError('Hold entry, timing or camera differs from native adapters')
        frost_slots=config.get('frost_variants',[])
        if not isinstance(frost_slots,list):
            raise ValueError('Frost Moon requires three variant slots')
        hold_keys = [adapters[index-1]['player_key'] for index in hold_slots if index not in frost_slots and index not in [binding['variant'] for binding in config.get('skill_bindings',[])]]
        if len(set(hold_keys)) != len(hold_keys):
            raise ValueError('Only one held entry may own a player stance opener')
        for index, adapter in enumerate(adapters):
            if adapter is None or adapter['kind'] != 4:
                continue
            # Continuations share both the stance template and retained resource owner.
            # A matching action key in another package cannot inherit this native chain.
            # Source rows select the actual successor; this check only bounds ownership.
            fields = (*ADAPTER_POINTERS, 'player_key', 'player_motion', 'transition_count', 'recovery_frame')
            if not any(all(adapter[field] == adapters[slot-1][field] for field in fields) for slot in hold_slots):
                raise ValueError('Native continuation has no matching held-entry owner')
    elif hold_slots or paired_slots or any(adapter is not None and adapter['kind'] == 4 for adapter in adapters) or hold_milliseconds or hold_camera:
        raise ValueError('Disabled hold configuration must contain no hold dependencies')
    imports.extend([0] * (len(MOVE_IMPORT.unpack(bytes(MOVE_IMPORT.size))) * (IMPORT_LIMIT-len(moves))))
    encoded_adapters.extend([0] * (11 * (IMPORT_LIMIT-len(moves))))
    native_grapple = config.get('native_grapple', False)
    if type(native_grapple) is not bool:
        raise ValueError('Native grapple enable setting must be a boolean')
    if native_grapple and not any(move['key'] == 0x361 and move['motion'] == 1311
                                  and move['flags'] == 0x8078000000 and adapter is None
                                  for move, adapter in zip(moves, adapters)):
        raise ValueError('Native grapple requires the retained Okatsu paired follow-through')
    native_bindings=int(native_grapple)
    if type(config.get('mid_light_ender',False)) is not bool:
        raise ValueError('Mid light ender must be a boolean')
    if config.get('mid_light_ender',False): native_bindings|=4
    bindings=config.get('skill_bindings',[]);encoded_bindings=[]
    if not isinstance(bindings,list) or len(bindings)>8: raise ValueError('Too many skill bindings')
    occupied=set()
    for binding in bindings:
        fields=[binding[field] for field in ('kind','stances','variant','key','motion','transition_count','flags')]
        kind,stances,variant,key,motion,rows,flags=fields
        if any(type(value) is not int for value in fields) or kind not in (1,2,3) or not 0<stances<8 or not 0<variant<=len(moves):
            raise ValueError('Invalid compiled skill binding')
        adapter=adapters[variant-1]
        if adapter is None and (kind==3 or moves[variant-1]['flags']!=0x184C0000):
            raise ValueError('Skill binding requires an ordinary executable entry')
        if adapter is not None and adapter['kind']!=5 and not (kind==1 and key==0xBC8 and adapter['kind']==1 and adapter['player_key']==0xCF6 and stances==1) and (adapter['kind']!=2 or stances!=1<<list(STANCE_OPENERS.values()).index(adapter['player_key'])):
            raise ValueError('Skill binding and graph stance differ')
        if kind==1 and (key,motion,rows,flags) not in NATIVE_SKILLS.values() or kind>=2 and any((key,motion,rows,flags)):
            raise ValueError('Unverified native skill signature')
        for stance in range(3):
            if not stances&(1<<stance): continue
            identity=(kind,key,stance)
            if identity in occupied: raise ValueError('Overlapping native skill bindings')
            occupied.add(identity)
        encoded_bindings.extend(fields)
    encoded_bindings.extend([0]*(7*(8-len(bindings))))
    hold_stances=config.get('hold_stances',7 if hold_variant else 0)
    frost=config.get('frost_variants',[0,0,0]); window=config.get('frost_milliseconds',750)
    speed=config.get('frost_speed',8)
    if type(speed) is not int or not 1<=speed<=8:
        raise ValueError('Frost Moon startup speed must be from 1 to 8')
    if type(hold_stances) is not int or not 0<=hold_stances<=7 or type(window) is not int or window!=0 and not 100<=window<=1500:
        raise ValueError('Invalid skill binding mask or Frost Moon window')
    if sum(b['stances'] for b in bindings if b['kind']==3)!=hold_stances:
        raise ValueError('Held stance mask differs from explicit bindings')
    if not isinstance(frost,list) or len(frost)!=3:
        raise ValueError('Frost Moon requires three variant slots')
    for slot,key in zip(frost,STANCE_OPENERS.values()):
        if type(slot) is not int or not 0<=slot<=len(moves) or slot and (slot not in hold_slots or adapters[slot-1]['player_key']!=key):
            raise ValueError('Frost Moon variant must match its stance skill')
    profiles=config.get('launch_profiles',LAUNCH_PROFILES); boost=config.get('air_juggle_boost',AIR_JUGGLE_BOOST)
    validate_launch_profiles(profiles,boost)
    tracking=config.get('tracking_rates',TRACKING_RATES)
    validate_tracking_rates(tracking)
    launch=[value for profile in profiles for value in (profile['resistance_below'],profile['weight_scale'],profile['vertical_impulse'],0)]
    return SESSION_CONFIG.pack(MAGIC, VERSION, SESSION_CONFIG.size, pid,
                               int(creation_filetime), int(tag, 16), hold_variant, hold_milliseconds, hold_camera, native_bindings,
                               hold_stances,*frost,window,speed,*pointers,
                               len(moves), string_variant, *imports, *encoded_adapters, *encoded_bindings, *launch, boost, *(tracking[key] for key in TRACKING_RATES))
