# Discover current actors and verify exact move/resource identities before enabling a moveset.
# Product definitions supply identities; source bytes and ownership checks remain authoritative.
# See CODE_GUIDE.md for the player-readable flow and terminology.
import argparse
from copy import deepcopy
import ctypes as C
from ctypes import wintypes as W
import json
import hashlib
import os
import re
from pathlib import Path
import struct
import sys

from project_paths import MOD_ROOT
CODE = Path(os.environ.get('TANTO_RUNTIME_CODE', Path(__file__).resolve().parent))
HERE = Path(os.environ.get('NIOH_RUNTIME_HOME', MOD_ROOT/'runtime'))
from boss_probe import LiveGame, U64, U32, I32, kernel
from nioh_memory import modules, current_pid
from project_paths import DATA
from profile_resources import StableReads, inspect_candidate, resources, inspect_motion, inspect_timing
from load_resources import load_resources, ResourceLoadError
from trace_reader import Trace
from action_banks import inspect_bank, inspect_banks, resolve
from move_imports import read_import_manifest, check_import_topology, GRAB_ATTEMPT_FLAGS, PLAYER_PAIRED_FLAGS, STANCE_OPENERS, PLAYER_TEMPLATES, IMPORT_LIMIT, is_izuna_bridge
from engine_policy import LAUNCH_PROFILES, TRACKING_RATES, AIR_JUGGLE_BOOST, FROST_MILLISECONDS, FROST_STARTUP_SPEED, KI_PULSE, validate_move_policy
from engine_config import validate_preset, read_json, atomic_json, move_label, HEAVY_STRINGS, NATIVE_SKILLS, HELD_MOVES, SPEED_MOVES, SOURCE_MANIFESTS

IMPORT_MANIFEST = DATA/'imports/okatsu.json'
CURRENT_CONFIG = HERE / 'controller-binding.json'


def require_stopped(pid):
    # Prevent preparation from learning temporarily borrowed slots.
    # Inspect loaded runtime namespaces and reject any active or busy trace.
    # Fresh originals must come from a recovered player generation.
    # Stop returning busy leaves the trace enabled. Do not learn borrowed slots
    # as the next session's originals, or prepare during an active observer.
    mappings = [(prefix, None) for prefix in ('NiohBossTrace_v1', 'NiohDispatchTrace_v1', 'NiohResearchTrace_v1', 'NiohBossRepeatTrace_v1')]
    retained = []
    # Previous workspaces and trainer installs can leave a live module behind.
    # Its loaded filename supplies the namespace even without our session cache.
    for module in modules(pid):
        name = module['name'].lower()
        match = re.fullmatch(r'boss_repeat_([0-9a-f]{16})\.dll', name)
        if match:
            mappings.append(('NiohBossRepeatTrace_v2', match[1]))
            retained.append((module, 'runtime'))
        elif re.fullmatch(r'resources_[0-9a-f]{16}_[0-9a-f]{64}\.dll', name):
            retained.append((module, 'resources'))
        elif name in ('boss_repeat.dll', 'nioh_skill_runtime.dll'):
            raise ValueError(f'Loaded runtime {module["path"]} has no discoverable session tag; preserve its current session before preparation')
    if (HERE / 'boss-session.json').exists():
        try:
            prior = json.loads((HERE / 'boss-session.json').read_text())
            tag = prior.get('config_tag')
            if isinstance(tag, str) and re.fullmatch('[0-9a-f]{16}', tag) and prior['session']['pid'] == pid:
                mappings.append(('NiohBossRepeatTrace_v2', tag))
        except (OSError, ValueError, KeyError, TypeError):
            pass  # Loaded-module namespaces remain authoritative after a bad cache.
    for prefix, tag in dict.fromkeys(mappings):
        try:
            trace = Trace(pid, prefix, tag)
        except OSError as error:
            if getattr(error, 'winerror', None) == 2:
                continue  # No prior mapping in this process.
            raise
        try:
            state = trace.header()
            if state['enabled'] or state['status'] != 0:
                raise ValueError(f'{prefix} is active or not cleanly stopped; finish Stop before preparation')
        finally:
            trace.close()
    # Stop restores gameplay state but deliberately retains native modules and their callbacks.
    # Do not mix a newly compiled Engine with older retained code in the same game process.
    expected = {}
    for module, kind in retained:
        if kind not in expected:
            expected[kind] = (native_code_hash() if kind == 'runtime' else
                hashlib.sha256((CODE/'native/build/nioh_resources.dll').read_bytes()).hexdigest())
        try:
            actual = hashlib.sha256(Path(module['path']).read_bytes()).hexdigest()
        except OSError as error:
            raise ResourceLoadError('Cannot verify a retained MWM module. Restart Nioh before enabling this version.') from error
        if actual != expected[kind]:
            raise ResourceLoadError('A different MWM Engine build is still loaded. Restart Nioh before enabling this version; Disable alone cannot unload retained native code.')


def resolve_imports(game, stable, bank, motion_bank, timing_wrapper, manifest):
    # Resolve configured moves against retained native resources.
    # Pin descriptors, transitions, motion/timing entries and exact voice events.
    # Manifest mismatches are rejected before publishing executable adapters.
    source_bank = inspect_bank(game, bank)
    bank_header = stable.pin(bank + 0x128, 12)
    table, count = U64(bank_header, 0), U32(bank_header, 8)
    if table != int(source_bank['table'], 0) or count != source_bank['count']:
        raise ValueError('Owned action table changed during import lookup')
    if not 0 < count <= 4096:
        raise ValueError('Owned action count exceeds native import bounds')
    expected = bytearray(count * 8)
    for entry in source_bank['records']:
        struct.pack_into('<Q', expected, entry['position'] * 8, int(entry['descriptor'], 0))
    stable.pin(table, count * 8, bytes(expected))
    entries = dict(banks=[source_bank])
    resolved, imports = [], []
    for move in manifest['moves']:
        key, motion_key = move['key'], move['motion']
        entry = resolve(entries, key)
        if entry is None:
            raise ValueError(f'Loaded source has no enabled action {key:X}')
        descriptor, payload = int(entry['descriptor'], 0), int(entry['payload'], 0)
        desc, body = stable.pin(descriptor, 0xD0), stable.pin(payload, 0xB0)
        if U32(desc, 0) != key or not desc[0x40] or U64(desc, 0x20) != payload:
            raise ValueError('Loaded source action identity differs')
        if U64(body, 0x18) != move['flags']:
            raise ValueError('Loaded source action family differs from the configured adapter')
        if 'source_payload_prefix' in move and not body.startswith(bytes.fromhex(move['source_payload_prefix'])):
            raise ValueError('Loaded unobserved branch payload differs from exact archive evidence')
        if I32(body, 0x20) != motion_key or I32(body, 0x34) not in (-1, motion_key):
            raise ValueError('Loaded source motion/timing identity differs')
        if struct.unpack_from('<h', body, 0x24)[0] != move['recovery_frame']:
            raise ValueError('Loaded source recovery frame differs')
        if struct.unpack_from('<h', body, 0x16)[0] != move['ki_cost']:
            raise ValueError('Loaded source Ki cost differs')
        start, transitions = struct.unpack_from('<HH', desc, 0x80)
        if (move['transition_count'] is not None and transitions != move['transition_count']
                or not 1 <= transitions <= (128 if move.get('adapter_kind') in (1,2,4) else 28)
                or start + transitions > 65536):
            raise ValueError('Loaded source transition count differs')
        pointers = stable.pin(U64(desc, 0x78) + start * 8, transitions * 8)
        rows = [stable.pin(U64(pointers, i * 8), 0x30) for i in range(transitions)]
        if 'native_followups' in move:
            by_id = {item['id']: item for item in manifest['moves']}
            for target in move['native_followups']:
                if target not in by_id or not any(struct.unpack_from('<h', row, 0x14)[0] == by_id[target]['key']
                        and (((move['key']==0xBBF or 0xC63<=move['key']<=0xC65) and row[10:13]==b'\x02\x00\x01') or row[11] == 0xff and (row[10] == 1 or struct.unpack_from('<H', row)[0] == 20
                              or (move['flags'] == PLAYER_PAIRED_FLAGS or move['key'] in (0xC73,0xC82)) and struct.unpack_from('<H', row)[0] == 0
                            or row[10] == 0 and row[:10] == b'\xff'*10)) for row in rows):
                    raise ValueError('Configured native continuation is absent from the source rows')
            if move['id']=='jin_hayabusa.izuna_drop' and not any(
                    struct.unpack_from('<HH',row)==(20,207) and row[10:12]==b'\x02\xff'
                    and struct.unpack_from('<h',row,20)[0]==0xC7A
                    and struct.unpack_from('<hh',row,32)==(-32768,26) for row in rows):
                raise ValueError('Izuna launcher lacks its recorded airborne continuation')
        if move['next_variant'] != -1:
            next_key = manifest['moves'][move['next_variant']]['key']
            if move['flags'] == GRAB_ATTEMPT_FLAGS or move.get('adapter_kind') == 2 or is_izuna_bridge(move):
                native_success = any(struct.unpack_from('<h', row, 0x14)[0] == next_key
                                     and struct.unpack_from('<H', row, 0)[0] == 22
                                     and row[10:12]==b'\x00\xff' for row in rows)
                if not native_success:
                    raise ValueError('Configured paired success is absent from native grab transitions')
            elif not any(struct.unpack_from('<h', row, 0x14)[0] == next_key
                         and struct.unpack_from('<hh', row, 0x20) == (move['next_start'], move['next_end']) for row in rows):
                    raise ValueError('Configured combo window is absent from source transitions')
        if move['flags'] == PLAYER_PAIRED_FLAGS:
            paired = {item['key'] for item in manifest['moves'] if item['flags'] == PLAYER_PAIRED_FLAGS}
            source_paired = {struct.unpack_from('<h', row, 0x14)[0] for row in rows
                             if 0x3B2 <= struct.unpack_from('<h', row, 0x14)[0] <= 0x3B7}
            if not source_paired <= paired:
                raise ValueError('Native paired transition targets an unconfigured source action')
        motion = inspect_motion(game, stable, motion_bank, motion_key)
        timing = inspect_timing(game, stable, timing_wrapper, motion_key)
        if motion['presence'] != 'present' or timing['presence'] != 'present':
            raise ValueError('Owned source package did not resolve the move')
        record = int(timing['record'], 0)
        header = stable.pin(record, 0x24)
        event_count, event_offset, sound_offset = U32(header, 4), U32(header, 8), U32(header, 0x10)
        if not 0 < event_count <= 512 or not 0x24 <= event_offset <= 0x10000:
            raise ValueError('Source timing event bounds differ')
        if not event_offset + event_count * 12 <= sound_offset <= 0x10000:
            raise ValueError('Source timing sound bounds differ')
        events = list(struct.iter_unpack('<III', stable.pin(record + event_offset, event_count * 12)))
        # Known William cues need source verification without voice replacement.
        # The runtime voice list contains only cues requiring the player adapter.
        for voice in move['source_voices'] if 'source_voices' in move else move['voices']:
            if events.count((voice['frame'], 10, voice['index'])) != 1:
                raise ValueError('Configured voice event differs from source timing')
            sound = stable.pin(record + sound_offset + voice['index'] * 0x4c, 0x4c)
            if U32(sound, 0x1c) != voice['hash'] or U32(sound, 0x40) != 12:
                raise ValueError('Configured voice hash/category differs from source timing')
        resolved.append(dict(key=key, motion=motion_key, resolution=entry,
                             motion_resource=motion, timing_resource=timing))
        imports.append(dict(move, transition_count=transitions, descriptor=descriptor, payload=payload,
                            clip=int(motion['clip'], 0), timing_record=record))
    return resolved, imports


def configured_imports(configuration):
    # Keep the two chord slots and only the enabled Okatsu dependencies.
    # The disabled standalone string contributes no runtime descriptors or voice copies.
    # Whole source packages stay retained because their internal data is shared.
    manifest=read_import_manifest(IMPORT_MANIFEST)
    if not configuration['string_enabled']:
        manifest['moves']=[move for index,move in enumerate(manifest['moves'])
                           if index<2 or configuration['okatsu_grapple'] and move['key']==0x361]
        manifest['string_variant']=0
    return manifest


def configured_replacements(configuration=None, baseline=None):
    # Resolve one validated sword preset into native imports and stance templates.
    # Expand selected strings once and derive every runtime index from stable IDs.
    # Disabling low-heavy taps must not disable an independent held skill.
    configuration = validate_preset(configuration if configuration is not None else read_json(CURRENT_CONFIG))
    candidate = HEAVY_STRINGS.get(configuration['low_heavy'])
    entries=list(dict.fromkeys((stance,identifier) for bindings in ('stance_holds','frost_moon')
                               for stance,identifier in configuration[bindings].items() if identifier in HELD_MOVES))
    entries=list(dict.fromkeys(entries+[(binding['stance'],binding['move'])
        for binding in configuration['skill_bindings'] if binding['move'] in HELD_MOVES]+
        [(configuration['chord_stance'],configuration[field]) for field in ('tap_move','hold_move') if configuration[field] in HELD_MOVES]))
    hold = bool(entries)
    jump='jin_hayabusa.flying_swallow_jump' in (configuration['tap_move'],configuration['hold_move'],
        *configuration['frost_moon'].values(), *(binding['move'] for binding in configuration['skill_bindings']))
    if candidate is None and not hold and not jump:
        return None
    sources = [read_import_manifest(IMPORT_MANIFEST.with_name(source['boss_id']+'.json')) for source in SOURCE_MANIFESTS]
    manifest = dict(sources[0], moves=[], hold_chains={})
    for source in sources:
        offset = len(manifest['moves'])
        for move in source['moves']:
            if move['next_variant'] >= 0: move['next_variant'] += offset
        manifest['moves'].extend(source['moves'])
        manifest['hold_chains'].update(source['hold_chains'])
    chains={**{chain[0]:chain for chain in manifest['candidates'].values()},**manifest['hold_chains']}
    selected = list(manifest['candidates'][candidate]) if candidate else []
    by_id = {move['id']: move for move in manifest['moves']}
    if candidate and (len(selected) != 3 or len(set(selected)) != 3 or any(key not in by_id for key in selected)):
        raise ValueError(f'{move_label(configuration["low_heavy"])} has an incomplete Low Triangle / Y string definition. Restore its three recorded moves before enabling it.')
    if candidate and [by_id[key]['replacement']['player_key'] for key in selected] != [0xCF5, 0xCF6, 0xCF7]:
        raise ValueError(f'{move_label(configuration["low_heavy"])} has an incompatible Low Triangle / Y sequence. Restore its Low-stance move definition before enabling it.')
    if hold:
        for stance, identifier in entries:
            player_key=STANCE_OPENERS.get(stance, STANCE_OPENERS['low'])
            if (identifier not in by_id or by_id[identifier]['adapter_kind'] not in (1, 2)
                    or identifier not in chains):
                raise ValueError(f'{move_label(identifier)} cannot start from {stance.title()} stance with its current definition. Choose another move or restore its supported input definition.')
            chain = chains[identifier]
            if not isinstance(chain, list) or not chain or chain[0] != identifier or any(item not in by_id for item in chain):
                raise ValueError(f'{move_label(identifier)} has an incomplete move sequence. Restore its move definitions or choose another move before saving.')
            # Stance belongs to the binding, not the boss move's permanent identity.
            # Apply its verified William opener to the entry and ordinary continuations.
            # Native paired actions retain their partner-driven descriptors and no input template.
            for item in chain:
                move = by_id[item]
                if move['adapter_kind'] == 3:
                    continue
                move['adapter_kind'] = 2 if item == identifier else 4
                motion, count, recovery = PLAYER_TEMPLATES[player_key]
                move['replacement'] = dict(player_key=player_key, player_motion=motion,
                                           transition_count=count, recovery_frame=recovery)
            selected = selected + chain
    if jump: selected.append('jin_hayabusa.flying_swallow_jump')
    if len(set(selected)) != len(selected):
        duplicate=next(identifier for identifier in selected if selected.count(identifier)>1)
        raise ValueError(f'{move_label(duplicate)} appears in more than one selected move sequence. Disable one overlapping binding or choose a different move.')
    # Group selected dependencies by their resource owner; preserve order inside each graph.
    # Existing Jin layouts keep their indices; additional bosses never borrow Jin's bank.
    selected = [identifier for source in sources for identifier in selected if identifier.partition('.')[0]==source['boss_id']]
    baseline=baseline if baseline is not None else configured_imports(configuration)
    count=len(selected)+len(baseline['moves'])
    if count>IMPORT_LIMIT:
        raise ValueError(f'This moveset needs {count} move phases; the Engine supports {IMPORT_LIMIT}. Multi-part moves include all their follow-up phases. Disable an optional move or string to free slots before saving.')
    positions = {identifier:index for index,identifier in enumerate(selected)}
    all_moves = manifest['moves']
    manifest['moves'] = [by_id[key] for key in selected]
    for move in manifest['moves']:
        dependencies=move.get('native_followups',[])
        if not isinstance(dependencies,list) or any(not isinstance(identifier,str) for identifier in dependencies):
            raise ValueError(f'{move_label(move["id"])} has an invalid follow-up definition. Restore its move definitions before saving.')
        if move['next_variant'] != -1: dependencies=[*dependencies,all_moves[move['next_variant']]['id']]
        missing=next((identifier for identifier in dependencies if identifier not in positions),None)
        if missing:
            raise ValueError(f'{move_label(move["id"])} needs {move_label(missing)}, which is missing from the selected move sequence. Restore its complete move definition or choose another move before saving.')
        if move['next_variant'] != -1:
            move['next_variant'] = positions[all_moves[move['next_variant']]['id']]
    # Validate the complete table in live preparation's index space without changing replacement-local indices.
    combined=deepcopy(manifest['moves'])
    for move in combined:
        if move['next_variant']!=-1:move['next_variant']+=len(baseline['moves'])
    try:
        check_import_topology(baseline['moves']+combined,baseline['string_variant'])
    except ValueError as error:
        raise ValueError(f'The selected move sequences are incompatible: {error}. Restore the affected move definitions or choose different moves before saving.') from error
    manifest['hold_variant'] = next((index+1 for index,move in enumerate(manifest['moves'])
                                     if move['adapter_kind'] == 2), 0)
    manifest['hold_milliseconds'] = round(configuration['hold_seconds']*1000) if manifest['hold_variant'] else 0
    manifest['hold_stances'] = sum(1<<i for i,stance in enumerate(STANCE_OPENERS) if configuration['stance_holds'][stance])
    manifest['frost_variants'] = [positions[configuration['frost_moon'][stance]]+1 if configuration['frost_moon'][stance] in positions else 0 for stance in STANCE_OPENERS]
    manifest['frost_milliseconds'] = FROST_MILLISECONDS
    manifest['candidate'] = candidate
    return manifest


def compiled_skill_bindings(configuration, imports):
    # Resolve portable source/stance/move rules only after import slots are known.
    # Native skill identities follow the game's assignment and timing; chords follow selected input rows.
    # The native table carries exact signatures, never device button masks or guessed action IDs.
    slots={move['id']:index+1 for index,move in enumerate(imports)}
    result=[]
    for binding in configuration['skill_bindings']:
        source,stance,move=(binding[field] for field in ('source','stance','move'))
        scopes=list(STANCE_OPENERS) if source=='heavy_attack' and stance=='any' else [stance]
        for scope in scopes:
            key,motion,rows,flags=NATIVE_SKILLS.get(source,(0,0,0,0))
            if source=='heavy_attack':
                key=STANCE_OPENERS[scope]; motion,rows,_=PLAYER_TEMPLATES[key]
            result.append(dict(kind={'guard_light':2,'high_heavy_followup':4,'light_attack':5}.get(source,1),
                stances=7 if scope=='any' else 1<<list(STANCE_OPENERS).index(scope),
                variant=slots[move],key=key,motion=motion,transition_count=rows,flags=flags))
    for stance,move in configuration['stance_holds'].items():
        if move: result.append(dict(kind=3,stances=1<<list(STANCE_OPENERS).index(stance),variant=slots[move],key=0,motion=0,transition_count=0,flags=0))
    if len(result)>8: raise ValueError(f'This setup uses {len(result)} native override slots; only 8 are supported. Remove an override or held binding, or narrow an Any Heavy attack to one stance.')
    return result


def compiled_move_settings(configuration, imports, policy=None):
    # Build playback speed and Ki Pulse settings for each imported action phase.
    # A phase inherits its string's root settings unless it has its own reviewed override.
    # Paired animation flags force native speed and baseline Pulse settings so synchronized roles stay aligned.
    configuration=validate_preset(configuration)
    policy=validate_move_policy(policy if policy is not None else
        read_json(DATA/'move-policy.json',dict(schema_version=1,moves={})), SPEED_MOVES)
    chains={root:chain for manifest in SOURCE_MANIFESTS for root,chain in
            {**{chain[0]:chain for chain in manifest['candidates'].values()},**manifest['hold_chains']}.items()}
    present={move['id'] for move in imports}
    inherited={child:root for root,chain in chains.items() if root in present for child in chain}
    result=[]
    for move in imports:
        identifier=move['id']; root=inherited.get(identifier,identifier)
        settings=configuration['move_settings']
        speed=settings.get(identifier,settings.get(root,{})).get('speed',1)
        pulse=policy['moves'].get(identifier,policy['moves'].get(root,{})).get('ki_pulse',KI_PULSE)
        if move['flags'] in (0x8078000000,PLAYER_PAIRED_FLAGS): speed,pulse=1,KI_PULSE
        result.append(dict(speed=speed,**pulse))
    return result


def player_replacement(game, stable, player, move, group):
    # Pin the exact William descriptor and native transitions used by this replacement.
    # Resolve through current enabled banks and compare researched motion, recovery and flags.
    # Keeping William's transition table preserves normal input, stance and running-action routing.
    expected = move['replacement']
    entry = resolve(inspect_banks(game, int(player['actor'], 0)), expected['player_key'])
    if entry is None:
        raise ValueError('Required player stance-heavy descriptor is absent')
    descriptor, payload = int(entry['descriptor'], 0), int(entry['payload'], 0)
    desc, body = stable.pin(descriptor, 0xD0), stable.pin(payload, 0xB0)
    if U32(desc, 0) != expected['player_key'] or not desc[0x40] or U64(desc, 0x20) != payload:
        raise ValueError('Player replacement descriptor identity changed')
    start, count = struct.unpack_from('<HH', desc, 0x80)
    if (count != expected['transition_count'] or not 1 <= count <= 64 or start + count > 65536
            or I32(body, 0x20) != expected['player_motion']
            or struct.unpack_from('<h', body, 0x24)[0] != expected['recovery_frame']
            or U64(body, 0x18) != 0x8000000594C0000):
        raise ValueError('Player replacement source signature differs from recorded stance heavy')
    pointers = stable.pin(U64(desc, 0x78) + start * 8, count * 8)
    for index in range(count):
        stable.pin(U64(pointers, index * 8), 0x30)
    return dict(group, player_descriptor=descriptor, kind=move['adapter_kind'], **expected)


def fresh_profile(game):
    # Profile the current player using engine-owned source packages.
    # Resolve imports and camera slot zero, then recheck all pinned identities.
    # Boss objects and stale session pointers never supply resources.
    configuration = validate_preset(read_json(CURRENT_CONFIG))
    manifest = configured_imports(configuration)
    replacement_manifest = configured_replacements(configuration,manifest)
    action_resource, timing_resource, motion_bank, camera_bank, node, owner = load_resources(game, motion_keys=[move['motion'] for move in manifest['moves']])
    replacement_handles = {}
    if replacement_manifest is not None:
        for boss in dict.fromkeys(move['id'].partition('.')[0] for move in replacement_manifest['moves']):
            handles = load_resources(game, DATA/'resources'/f'{boss}.json',
                [move['motion'] for move in replacement_manifest['moves'] if move['id'].partition('.')[0]==boss])
            if handles[-2:] != (node, owner):
                raise ValueError('Player identity changed between resource-profile loads')
            replacement_handles[boss] = handles
    game.begin_sample()
    stable = StableReads(game)
    player = inspect_candidate(game, stable, dict(object=hex(node), owner_like=hex(owner)))
    if player['role'] != 'player_fingerprint':
        raise ValueError('Native player candidate changed before profiling')
    bank = U64(stable.pin(action_resource + 0x468, 8), 0)
    timing_wrapper = U64(stable.pin(timing_resource + 0x468, 8), 0)
    moves, imports = resolve_imports(game, stable, bank, motion_bank, timing_wrapper, manifest)
    adapters = [None] * len(imports)
    hold_variant = hold_milliseconds = hold_camera_bank = 0
    hold_stances=0; frost_variants=[0,0,0]; frost_milliseconds=FROST_MILLISECONDS
    base = int(game.identity['module_base'], 0)
    if U64(stable.pin(camera_bank, 8), 0) != base + 0x13C8FA0:
        raise ValueError('Owned camera resource has an unexpected type')
    camera_move = inspect_motion(game, stable, camera_bank, 1311)
    if camera_move['presence'] != 'present':
        raise ValueError('Owned camera package did not resolve the grab camera')
    player_camera = U64(stable.pin(owner + 0x48, 8), 0)
    camera_index = I32(stable.pin(player_camera + 0x20, 4), 0)
    if not 0 <= camera_index <= 2:
        raise ValueError('Player camera bank index is outside supported bounds')
    # The private imported context selects bank0 when the setter commits an
    # action. William's current idle/weapon camera index1/2 is not that bank.
    camera_slot = player_camera + 8
    camera_original = U64(stable.pin(camera_slot, 8), 0)
    info, motion_banks, timing_banks = resources(game, stable, player)
    for kind, banks in (('motion', motion_banks), ('timing', timing_banks)):
        info[kind] = dict(banks=[dict(slot=i, **{('bank' if kind == 'motion' else 'wrapper'):hex(address)})
                                for i, address in enumerate(banks)])
    player['resources'] = info
    source = dict(action_resource=hex(action_resource), timing_resource=hex(timing_resource),
                  action_resolution=moves[0]['resolution'], motion_key=moves[0]['motion'],
                  resources={kind:dict(banks=[dict(slot=0, **moves[0][kind+'_resource'])], present_slots=[0])
                             for kind in ('motion', 'timing')})
    replacement_offset = len(imports)
    for boss, handles in replacement_handles.items():
        actions, timing, motion, hold_camera, _, _ = handles
        # Resolve each source bank independently; repeated action keys across bosses are unrelated.
        # Rebase explicit paired links into this group's local manifest, then into the final table.
        # Every resource owner remains tied to the same verified William generation.
        subset = [deepcopy(move) for move in replacement_manifest['moves'] if move['id'].partition('.')[0]==boss]
        group_offset = len(imports)-replacement_offset
        for move in subset:
            if move['next_variant'] >= 0: move['next_variant'] -= group_offset
        source_manifest = dict(replacement_manifest, moves=subset)
        group = dict(action_resource=actions, timing_resource=timing,
                     bank=U64(stable.pin(actions + 0x468, 8), 0), motion_bank=motion,
                     timing_wrapper=U64(stable.pin(timing + 0x468, 8), 0))
        for resource, expected in ((actions, 0x13C7970), (timing, 0x12C5408), (motion, 0x13C8FA0)):
            if U64(stable.pin(resource, 8), 0) != base + expected:
                raise ValueError('Replacement resource has an unexpected native type')
        _, additional = resolve_imports(game, stable, group['bank'], motion, group['timing_wrapper'], source_manifest)
        for move in additional:
            if move['adapter_kind'] in (3,5):
                adapters.append(dict(group,kind=move['adapter_kind'],player_descriptor=0,player_key=0,player_motion=0,transition_count=0,recovery_frame=0))
            else:
                adapters.append(player_replacement(game, stable, player, move, group))
            if move['next_variant'] != -1:
                move['next_variant'] += len(imports)
        if replacement_manifest['hold_variant']:
            hold_variant = replacement_offset + replacement_manifest['hold_variant']
            hold_milliseconds = replacement_manifest['hold_milliseconds']
            hold_stances=replacement_manifest['hold_stances']
            frost_variants=[slot+replacement_offset if slot else 0 for slot in replacement_manifest['frost_variants']]
            frost_milliseconds=replacement_manifest['frost_milliseconds']
            if any(move['adapter_kind']==3 for move in additional):
                if U64(stable.pin(hold_camera,8),0)!=base+0x13C8FA0 or inspect_motion(game,stable,hold_camera,5020)['presence']!='present':
                    raise ValueError('Owned Jin paired camera5020 is unavailable')
                hold_camera_bank=hold_camera
        imports.extend(additional)
    native_grapple = configuration['okatsu_grapple']
    slots={move['id']:index+1 for index,move in enumerate(imports)}
    frost_variants=[slots.get(move,0) for move in configuration['frost_moon'].values()]
    from game_controller import controller_selection
    selection=controller_selection(read_json(HERE/'controller-calibration.json',{}))
    stable.check()
    return dict(session=game.identity, player=player, source=source, charged_candidate=moves[1], preset=configuration,
                imports=imports, adapters=adapters, string_variant=manifest['string_variant'],
                hold_variant=hold_variant, hold_milliseconds=hold_milliseconds, hold_camera_bank=hold_camera_bank,
                hold_stances=hold_stances, frost_variants=frost_variants, frost_milliseconds=frost_milliseconds,
                frost_speed=FROST_STARTUP_SPEED,launch_profiles=LAUNCH_PROFILES,air_juggle_boost=AIR_JUGGLE_BOOST,tracking_rates=TRACKING_RATES,
                move_settings=compiled_move_settings(configuration,imports),controller_selection=selection,
                camera=dict(source_bank=hex(camera_bank), player_slot=hex(camera_slot),
                            original=hex(camera_original), source_clip=camera_move['clip']),
                resource_ownership='engine_retained', source_actor_required=False, native_grapple=native_grapple,
                mid_light_ender=configuration['mid_light_ender'],
                skill_bindings=compiled_skill_bindings(configuration,imports))


def boss_fields(profile):
    # Translate profiled relationships into the runtime ABI fields.
    # Extract player/source pointers and the four resource-slot originals.
    # Missing ownership data cannot become an executable session.
    source, player, charge = profile['source'], profile['player'], profile['charged_candidate']
    motion = source['resources']['motion']['banks'][0]
    timing = source['resources']['timing']['banks'][0]
    pulse = next(a for a in player['target_actions'] if a['action_key'] == 0xCF0)
    fields = dict(player=int(player['actor'],0), player_owner=int(player['owner'],0),
        source_action_resource=int(source['action_resource'],0), source_timing_resource=int(source['timing_resource'],0),
        vtable=int(profile['session']['vtable'],0), source_bank=int(source['action_resolution']['bank_address'],0),
        source_descriptor=int(source['action_resolution']['descriptor'],0), source_payload=int(source['action_resolution']['payload'],0),
        source_motion_bank=int(motion['bank'],0), source_timing_wrapper=int(timing['wrapper'],0),
        source_clip=int(motion['clip'],0), source_timing_record=int(timing['record'],0),
        player_motion=int(player['resources']['motion_object'],0), player_timing=int(player['resources']['timing_object'],0),
        charge_descriptor=int(charge['resolution']['descriptor'],0), charge_payload=int(charge['resolution']['payload'],0),
        charge_clip=int(charge['motion_resource']['clip'],0), charge_timing_record=int(charge['timing_resource']['record'],0),
        player_pulse_descriptor=int(pulse['resolution']['descriptor'],0),
        source_camera_bank=int(profile['camera']['source_bank'],0),
        player_camera_slot=int(profile['camera']['player_slot'],0),
        camera_original=int(profile['camera']['original'],0))
    originals = [int(player['resources']['motion']['banks'][i]['bank'],0) for i in (0,4)]
    originals += [int(player['resources']['timing']['banks'][i]['wrapper'],0) for i in (0,3)]
    if any(p < 0x10000 for key,p in fields.items() if key != 'camera_original') or any(p < 0x10000 for p in originals):
        raise ValueError('Required player/source resource absent')
    if fields['camera_original'] and fields['camera_original'] < 0x10000:
        raise ValueError('Original camera resource is neither absent nor a valid pointer')
    fields.update(imports=profile['imports'], adapters=profile['adapters'], string_variant=profile['string_variant'])
    fields.update((field,profile[field]) for field in ('hold_variant','hold_milliseconds','hold_camera_bank'))
    fields['native_grapple'] = profile.get('native_grapple', False)
    fields['mid_light_ender']=profile.get('mid_light_ender',False)
    fields['skill_bindings']=profile.get('skill_bindings',[])
    fields['move_settings']=profile.get('move_settings')
    fields['controller_selection']=profile.get('controller_selection',0)
    fields.update((field,profile[field]) for field in ('hold_stances','frost_variants','frost_milliseconds','frost_speed','launch_profiles','air_juggle_boost','tracking_rates'))
    return fields, originals


def native_code_hash():
    # Identify the binary pinned for this play session.
    # Hash the supervisor's snapshot, with source hashing only for offline tooling.
    # Editing sources cannot relabel a DLL already running in the game.
    # The supervisor pins a completed binary for all retries. Source edits must
    # not relabel that running build, and portable releases contain no sources.
    pinned = os.environ.get('NIOH_RUNTIME_BUILD_DLL')
    binary = Path(pinned) if pinned else HERE / 'native/build/nioh_skill_runtime.dll'
    if pinned or binary.is_file():
        return hashlib.sha256(binary.read_bytes()).hexdigest()
    digest = hashlib.sha256()
    for path in sorted((CODE / 'native').glob('*')):
        if path.suffix in ('.h', '.cpp') and path.name != 'boss_session.h':
            digest.update(path.name.encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def config_tag(fields, originals):
    # Give each configuration and binary pair a stable module namespace.
    # Hash ordered session fields, originals and the native code identity.
    # Reattachment reuses the right module instead of colliding with old state.
    digest = hashlib.sha256(json.dumps([fields, originals], sort_keys=True).encode())
    digest.update(native_code_hash().encode())
    return digest.hexdigest()[:16]


def main():
    # Prepare one current-player generation for the source launcher.
    # Require stopped hooks, resolve owned resources and publish both session files.
    # No mission-specific DLL compilation or controller calibration occurs.
    parser = argparse.ArgumentParser(description='Attach engine resources and reacquire the current player')
    parser.add_argument('--pid', type=int, help='Optional exact process; otherwise discover nioh.exe')
    parser.add_argument('--outdir', type=Path, default=HERE)
    args = parser.parse_args()
    if C.sizeof(C.c_void_p) != 8:
        parser.error('64-bit Python is required')
    pid = args.pid if args.pid is not None else current_pid()
    require_stopped(pid)
    with LiveGame(pid) as game:  # Exact executable hash, birth, RTTI and instruction guards.
        result = fresh_profile(game)
        fields, originals = boss_fields(result)
        require_stopped(pid)
    boss = dict(session=result['session'], **fields, originals=originals, config_tag=config_tag(fields, originals),
                scope='Engine-owned resources; current player generation')
    atomic_json(args.outdir / 'session-profile.json', result)
    atomic_json(args.outdir / 'boss-session.json', boss)
    print(f"Prepared player {fields['player']:#x}; engine owns action, motion and timing resources")


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, StopIteration, struct.error) as error:
        print(json.dumps(dict(status='error', stage='session_preparation', message=str(error),
                              retryable=not isinstance(error, ResourceLoadError))), file=sys.stderr)
        raise SystemExit(1)
