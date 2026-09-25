import argparse
import ctypes as C
from ctypes import wintypes as W
import json
import hashlib
import os
import re
from pathlib import Path
import struct
import sys

CODE = Path(__file__).resolve().parent
HERE = Path(os.environ.get('NIOH_RUNTIME_HOME', CODE))
from boss_probe import LiveGame, U64, U32, I32, kernel
from nioh_memory import modules
from profile_resources import StableReads, inspect_candidate, resources, inspect_motion, inspect_timing
from load_resources import load_resources
from trace_reader import Trace
from action_banks import inspect_bank, inspect_banks, resolve
from move_imports import read_import_manifest, GRAB_ATTEMPT_FLAGS, PLAYER_PAIRED_FLAGS, STANCE_OPENERS, PLAYER_TEMPLATES, IMPORT_LIMIT, is_izuna_bridge
from engine_config import validate_preset, read_json, atomic_json, HEAVY_STRINGS

IMPORT_MANIFEST = CODE.parent / 'catalogue/imports/okatsu.json'
CURRENT_CONFIG = HERE / 'controller-binding.json'


class PROCESSENTRY32W(C.Structure):
    _fields_ = [('dwSize', W.DWORD), ('cntUsage', W.DWORD), ('th32ProcessID', W.DWORD),
                ('th32DefaultHeapID', C.c_size_t), ('th32ModuleID', W.DWORD),
                ('cntThreads', W.DWORD), ('th32ParentProcessID', W.DWORD),
                ('pcPriClassBase', W.LONG), ('dwFlags', W.DWORD), ('szExeFile', W.WCHAR * 260)]


def current_pid():
    # Find the single current Nioh process without a saved PID.
    # Enumerate processes and reject zero or multiple matching executables.
    # Attachment must not guess between concurrent game instances.
    kernel.Process32FirstW.argtypes = [W.HANDLE, C.POINTER(PROCESSENTRY32W)]
    kernel.Process32FirstW.restype = W.BOOL
    kernel.Process32NextW.argtypes = kernel.Process32FirstW.argtypes
    kernel.Process32NextW.restype = W.BOOL
    handle = kernel.CreateToolhelp32Snapshot(2, 0)
    if handle == C.c_void_p(-1).value:
        raise C.WinError(C.get_last_error())
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = C.sizeof(entry)
        matches = []
        okay = kernel.Process32FirstW(handle, C.byref(entry))
        while okay:
            if entry.szExeFile.lower() == 'nioh.exe':
                matches.append(entry.th32ProcessID)
            okay = kernel.Process32NextW(handle, C.byref(entry))
        error = C.get_last_error()
        if error != 18:  # ERROR_NO_MORE_FILES
            raise C.WinError(error)
        if len(matches) != 1:
            raise ValueError(f'Expected exactly one running nioh.exe; found {len(matches)}')
        return matches[0]
    finally:
        kernel.CloseHandle(handle)


def require_stopped(pid):
    # Prevent preparation from learning temporarily borrowed slots.
    # Inspect loaded runtime namespaces and reject any active or busy trace.
    # Fresh originals must come from a recovered player generation.
    # Stop returning busy leaves the trace enabled. Do not learn borrowed slots
    # as the next session's originals, or prepare during an active observer.
    mappings = [(prefix, None) for prefix in ('NiohBossTrace_v1', 'NiohDispatchTrace_v1', 'NiohResearchTrace_v1', 'NiohBossRepeatTrace_v1')]
    # Previous workspaces and trainer installs can leave a live module behind.
    # Its loaded filename supplies the namespace even without our session cache.
    for module in modules(pid):
        name = module['name'].lower()
        match = re.fullmatch(r'boss_repeat_([0-9a-f]{16})\.dll', name)
        if match:
            mappings.append(('NiohBossRepeatTrace_v2', match[1]))
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
                or not 1 <= transitions <= (128 if move['flags'] in (0x194C0000, 0x200194C0000) else 28)
                or start + transitions > 65536):
            raise ValueError('Loaded source transition count differs')
        pointers = stable.pin(U64(desc, 0x78) + start * 8, transitions * 8)
        rows = [stable.pin(U64(pointers, i * 8), 0x30) for i in range(transitions)]
        if 'native_followups' in move:
            by_id = {item['id']: item for item in manifest['moves']}
            for target in move['native_followups']:
                if target not in by_id or not any(struct.unpack_from('<h', row, 0x14)[0] == by_id[target]['key']
                        and row[11] == 0xff and (row[10] == 1 or struct.unpack_from('<H', row)[0] == 20
                              or (move['flags'] == PLAYER_PAIRED_FLAGS or move['key']==0xC73) and struct.unpack_from('<H', row)[0] == 0
                            or row[10] == 0 and row[:10] == b'\xff'*10) for row in rows):
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


def configured_replacements(configuration=None):
    # Resolve one validated sword preset into native imports and stance templates.
    # Expand selected strings once and derive every runtime index from stable IDs.
    # Disabling low-heavy taps must not disable an independent held skill.
    configuration = validate_preset(configuration if configuration is not None else read_json(CURRENT_CONFIG))
    candidate = HEAVY_STRINGS.get(configuration['low_heavy'])
    entries=list(dict.fromkeys((stance,identifier) for bindings in ('stance_holds','frost_moon')
                               for stance,identifier in configuration[bindings].items() if identifier))
    hold = bool(entries)
    if candidate is None and not hold:
        return None
    manifest = read_import_manifest(IMPORT_MANIFEST.with_name('jin_hayabusa.json'))
    selected = list(manifest['candidates'][candidate]) if candidate else []
    by_id = {move['id']: move for move in manifest['moves']}
    if candidate and (len(selected) != 3 or len(set(selected)) != 3 or any(key not in by_id for key in selected)):
        raise ValueError('Jin candidate must select three distinct recorded moves')
    if candidate and [by_id[key]['replacement']['player_key'] for key in selected] != [0xCF5, 0xCF6, 0xCF7]:
        raise ValueError('Jin candidate must replace the three low-stance heavy descriptors in order')
    if hold:
        for stance, identifier in entries:
            player_key=STANCE_OPENERS[stance]
            if (identifier not in by_id or by_id[identifier]['adapter_kind'] not in (1, 2)
                    or identifier not in manifest['hold_chains']):
                raise ValueError('Held entry has no supported input adapter')
            chain = manifest['hold_chains'][identifier]
            if not isinstance(chain, list) or not chain or chain[0] != identifier or any(item not in by_id for item in chain):
                raise ValueError('Held entry has invalid native dependencies')
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
        if len(set(selected)) != len(selected) or len(selected) + 7 > IMPORT_LIMIT:
            raise ValueError('Selected holds duplicate imports or exceed the runtime table')
    positions = {identifier:index for index,identifier in enumerate(selected)}
    all_moves = manifest['moves']
    manifest['moves'] = [by_id[key] for key in selected]
    for move in manifest['moves']:
        if move['next_variant'] != -1:
            move['next_variant'] = positions[all_moves[move['next_variant']]['id']]
    manifest['hold_variant'] = next((index+1 for index,move in enumerate(manifest['moves'])
                                     if move['adapter_kind'] == 2), 0)
    manifest['hold_milliseconds'] = round(configuration['hold_seconds']*1000) if manifest['hold_variant'] else 0
    manifest['hold_stances'] = sum(1<<i for i,stance in enumerate(STANCE_OPENERS) if configuration['stance_holds'][stance])
    manifest['frost_variants'] = [positions[configuration['frost_moon'][stance]]+1 if configuration['frost_moon'][stance] else 0 for stance in STANCE_OPENERS]
    manifest['frost_milliseconds'] = round(configuration['frost_window_seconds']*1000)
    manifest['candidate'] = candidate
    return manifest


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
    replacement_manifest = configured_replacements(configuration)
    action_resource, timing_resource, motion_bank, camera_bank, node, owner = load_resources(game)
    replacement_handles = None
    if replacement_manifest is not None:
        replacement_handles = load_resources(game, IMPORT_MANIFEST.parent.parent / 'resource_profiles/jin_hayabusa.json')
        if replacement_handles[-2:] != (node, owner):
            raise ValueError('Player identity changed between resource-profile loads')
    game.begin_sample()
    stable = StableReads(game)
    player = inspect_candidate(game, stable, dict(object=hex(node), owner_like=hex(owner)))
    if player['role'] != 'player_fingerprint':
        raise ValueError('Native player candidate changed before profiling')
    bank = U64(stable.pin(action_resource + 0x468, 8), 0)
    timing_wrapper = U64(stable.pin(timing_resource + 0x468, 8), 0)
    manifest = read_import_manifest(IMPORT_MANIFEST)
    moves, imports = resolve_imports(game, stable, bank, motion_bank, timing_wrapper, manifest)
    adapters = [None] * len(imports)
    hold_variant = hold_milliseconds = hold_camera_bank = 0
    hold_stances=0; frost_variants=[0,0,0]; frost_milliseconds=750
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
    if replacement_handles is not None:
        actions, timing, motion, hold_camera, _, _ = replacement_handles
        group = dict(action_resource=actions, timing_resource=timing,
                     bank=U64(stable.pin(actions + 0x468, 8), 0), motion_bank=motion,
                     timing_wrapper=U64(stable.pin(timing + 0x468, 8), 0))
        for resource, expected in ((actions, 0x13C7970), (timing, 0x12C5408), (motion, 0x13C8FA0)):
            if U64(stable.pin(resource, 8), 0) != base + expected:
                raise ValueError('Replacement resource has an unexpected native type')
        _, additional = resolve_imports(game, stable, group['bank'], motion, group['timing_wrapper'], replacement_manifest)
        for move in additional:
            if move['adapter_kind'] == 3:
                adapters.append(dict(group,kind=3,player_descriptor=0,player_key=0,player_motion=0,transition_count=0,recovery_frame=0))
            else:
                adapters.append(player_replacement(game, stable, player, move, group))
            if move['next_variant'] != -1:
                move['next_variant'] += len(imports)
        if replacement_manifest['hold_variant']:
            hold_variant = len(imports) + replacement_manifest['hold_variant']
            hold_milliseconds = replacement_manifest['hold_milliseconds']
            hold_stances=replacement_manifest['hold_stances']
            frost_variants=[slot+len(imports) if slot else 0 for slot in replacement_manifest['frost_variants']]
            frost_milliseconds=replacement_manifest['frost_milliseconds']
            if any(move['adapter_kind']==3 for move in additional):
                if U64(stable.pin(hold_camera,8),0)!=base+0x13C8FA0 or inspect_motion(game,stable,hold_camera,5020)['presence']!='present':
                    raise ValueError('Owned Jin paired camera5020 is unavailable')
                hold_camera_bank=hold_camera
        imports.extend(additional)
    native_grapple = configuration['okatsu_grapple']
    stable.check()
    return dict(session=game.identity, player=player, source=source, charged_candidate=moves[1], preset=configuration,
                imports=imports, adapters=adapters, string_variant=manifest['string_variant'],
                hold_variant=hold_variant, hold_milliseconds=hold_milliseconds, hold_camera_bank=hold_camera_bank,
                hold_stances=hold_stances, frost_variants=frost_variants, frost_milliseconds=frost_milliseconds,
                frost_speed=configuration['frost_startup_speed'],
                camera=dict(source_bank=hex(camera_bank), player_slot=hex(camera_slot),
                            original=hex(camera_original), source_clip=camera_move['clip']),
                resource_ownership='engine_retained', source_actor_required=False, native_grapple=native_grapple,
                tiger_sprint=configuration['tiger_sprint'],mid_light_ender=configuration['mid_light_ender'])


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
    fields.update((field,profile.get(field,False)) for field in ('tiger_sprint','mid_light_ender'))
    fields.update((field,profile[field]) for field in ('hold_stances','frost_variants','frost_milliseconds','frost_speed'))
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
        print(json.dumps(dict(status='error', stage='read_only_preparation', message=str(error))), file=sys.stderr)
        raise SystemExit(1)
