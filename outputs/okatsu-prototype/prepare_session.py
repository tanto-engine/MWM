"""Refresh session-bound Okatsu resources using read-only game access.

Reuses controller-calibration.json unchanged. This does not build, load, or start
a DLL. Run while the previous hook is stopped and both encounter actors exist.
"""
import argparse
import ctypes as C
from ctypes import wintypes as W
import json
import hashlib
from pathlib import Path
import struct
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'boss-probe'))
from boss_probe import LiveGame, discover, U64, U32, I32, kernel
from profile_resources import profile as run_profile
from trace_reader import Trace
from action_banks import inspect_banks, resolve
from motion_resources import motion_lookup
from timing_resources import lookup as timing_lookup


class PROCESSENTRY32W(C.Structure):
    _fields_ = [('dwSize', W.DWORD), ('cntUsage', W.DWORD), ('th32ProcessID', W.DWORD),
                ('th32DefaultHeapID', C.c_size_t), ('th32ModuleID', W.DWORD),
                ('cntThreads', W.DWORD), ('th32ParentProcessID', W.DWORD),
                ('pcPriClassBase', W.LONG), ('dwFlags', W.DWORD), ('szExeFile', W.WCHAR * 260)]


def current_pid():
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
    # Stop returning busy leaves the trace enabled. Do not learn borrowed slots
    # as the next session's originals, or prepare during an active observer.
    mappings = [(prefix, None) for prefix in ('NiohBossTrace_v1', 'NiohDispatchTrace_v1', 'NiohResearchTrace_v1', 'NiohBossRepeatTrace_v1')]
    if (HERE / 'boss-session.json').exists():
        prior = json.loads((HERE / 'boss-session.json').read_text())
        if prior.get('config_tag') and prior['session']['pid'] == pid:
            mappings.append(('NiohBossRepeatTrace_v2', prior['config_tag']))
    for prefix, tag in mappings:
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


def fresh_profile(game, cached=None):
    reason = 'No saved session profile'
    if cached:
        try:
            if cached['session'] != game.identity:
                raise ValueError('Saved process identity differs')
            seed = dict(**game.identity, candidates=[
                dict(object=cached[role]['actor'], owner_like=cached[role]['owner'])
                for role in ('source', 'player')])
            return run_profile(game, seed), 'revalidated_profile', None
        except (OSError, ValueError, KeyError, TypeError, struct.error) as error:
            reason = str(error)
    print('Scanning current encounter actors; keep the game in the loaded encounter.', file=sys.stderr, flush=True)
    return run_profile(game, discover(game)), 'fresh_discovery', reason


def boss_fields(profile):
    source, player = profile['source'], profile['player']
    if (source['action_resolution']['key_u32'] != 0xC64 or source['motion_key'] != 1220
            or source['effective_timing_key'] != 1220 or player['motion_key'] != 2033):
        raise ValueError('Encounter does not match the researched Okatsu/player fingerprints')
    def slot(actor, kind, index):
        return next(row for row in actor['resources'][kind]['banks'] if row['slot'] == index)
    motion, timing = slot(source, 'motion', 0), slot(source, 'timing', 0)
    if motion['presence'] != 'present' or timing['presence'] != 'present':
        raise ValueError('Required source motion/timing slot 0 is not resolved')
    if not all(player['resources'][kind]['absent_from_all_loaded_banks'] for kind in ('motion', 'timing')):
        raise ValueError('Player banks already contain the source resource or could not be fully resolved')
    fields = dict(
        player=int(player['actor'], 0), player_owner=int(player['owner'], 0),
        source_actor=int(source['actor'], 0), source_owner=int(source['owner'], 0),
        vtable=int(profile['session']['vtable'], 0),
        source_bank=int(source['action_resolution']['bank_address'], 0),
        source_descriptor=int(source['action_resolution']['descriptor'], 0),
        source_payload=int(source['action_resolution']['payload'], 0),
        source_motion=int(source['resources']['motion_object'], 0),
        source_timing=int(source['resources']['timing_object'], 0),
        source_motion_bank=int(motion['bank'], 0), source_timing_wrapper=int(timing['wrapper'], 0),
        source_clip=int(motion['clip'], 0), source_timing_record=int(timing['record'], 0),
        player_motion=int(player['resources']['motion_object'], 0),
        player_timing=int(player['resources']['timing_object'], 0))
    originals = [int(slot(player, 'motion', index)['bank'], 0) for index in (0, 4)]
    originals += [int(slot(player, 'timing', index)['wrapper'], 0) for index in (0, 3)]
    if any(value < 0x10000 for value in [*fields.values(), *originals]):
        raise ValueError('Session contains an absent or invalid required pointer')
    return fields, originals


def validate_fields(game, profile, fields, originals):
    if game.identity != profile['session'] or not game.alive():
        raise ValueError('Profile process identity changed')
    game.begin_sample()
    for who in ('source', 'player'):
        actor = profile[who]
        raw, state = game.snapshot(int(actor['actor'], 0))
        if state['owner_like'] != actor['owner'] or [hex(U64(raw, 0x70+i*8)) for i in range(3)] != actor['action_banks']:
            raise ValueError('Actor/bank identity changed')
    for name, offset, expected in [
        ('source_owner', 0x38, fields['source_motion']), ('source_owner', 0x68, fields['source_timing']),
        ('player_owner', 0x38, fields['player_motion']), ('player_owner', 0x68, fields['player_timing']),
        ('source_motion', 8, fields['source_motion_bank']), ('source_timing', 0x10, fields['source_timing_wrapper'])]:
        if U64(game.bytes(fields[name]+offset, 8), 0) != expected:
            raise ValueError('Resource component changed')
    for address, expected in zip([fields['player_motion']+8, fields['player_motion']+0x28,
                                  fields['player_timing']+0x10, fields['player_timing']+0x28], originals):
        if U64(game.bytes(address, 8), 0) != expected:
            raise ValueError('Original resource slot changed')
    desc = game.bytes(fields['source_descriptor'], 0x44)
    if U32(desc, 0) != 0xC64 or not desc[0x40] or U64(desc, 0x20) != fields['source_payload']:
        raise ValueError('Source descriptor changed')
    if I32(game.bytes(fields['source_payload']+0x20, 4), 0) != 1220:
        raise ValueError('Source animation key changed')


def charge_fields(game, profile, fields):
    entry = resolve(inspect_banks(game, fields['source_actor']), 0xC66)
    if not entry or int(entry['bank_address'], 0) != fields['source_bank']:
        raise ValueError('Charged candidate is not in the verified source bank')
    payload = int(entry['payload'], 0)
    body = game.bytes(payload, 0xB0)
    if I32(body, 0x20) != 1230 or I32(body, 0x34) not in (-1, 1230):
        raise ValueError('Charged candidate motion/timing differs from researched values')
    motion = motion_lookup(game, fields['source_motion_bank'], 1230)
    timing = timing_lookup(game, fields['source_timing_wrapper'], 1230)
    fields.update(charge_descriptor=int(entry['descriptor'], 0), charge_payload=payload,
                  charge_clip=int(motion['clip'], 0), charge_timing_record=int(timing['record'], 0))
    pulse = next(a for a in profile['player']['target_actions'] if a['action_key'] == 0xCF0)
    fields['player_pulse_descriptor'] = int(pulse['resolution']['descriptor'], 0)
    profile['charged_candidate'] = dict(key=0xC66, motion=1230, resolution=entry,
                                       motion_resource=motion, timing_resource=timing,
                                       name='Okatsu Leaping Slash', binding='hold LB + Circle',
                                       visual_identity_confirmed=True)


def native_code_hash():
    digest = hashlib.sha256()
    for path in sorted((HERE / 'native').glob('*')):
        if path.suffix in ('.h', '.cpp') and path.name != 'boss_session.h':
            digest.update(path.name.encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def config_tag(fields, originals):
    digest = hashlib.sha256(json.dumps([fields, originals], sort_keys=True).encode())
    digest.update(native_code_hash().encode())
    return digest.hexdigest()[:16]


def session_header(fields, originals):
    lines = ['#pragma once', '// Session-bound preview only. Regenerate after any process/actor reload.',
             '#include <stdint.h>', f'static constexpr uint64_t BOSS_CONFIG_TAG = 0x{config_tag(fields, originals)}ULL;',
             'struct BossSession {']
    lines += [f'    uint64_t {name};' for name in fields]
    lines += ['    uint64_t originals[4];', '};', 'static BossSession boss_session = {']
    lines += [f'    0x{value:x}ULL, // {name}' for name, value in fields.items()]
    lines += ['    {' + ', '.join(f'0x{value:x}ULL' for value in originals) + '}', '};', '']
    return '\n'.join(lines)


def atomic_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf8', newline='\n', dir=path.parent,
                                         prefix=path.name+'.', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(text)
        temporary.replace(path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, help='Optional exact process; otherwise discover nioh.exe')
    parser.add_argument('--outdir', type=Path, default=HERE)
    parser.add_argument('--profile', type=Path, help='Optional cached profile to revalidate')
    args = parser.parse_args()
    if C.sizeof(C.c_void_p) != 8:
        parser.error('64-bit Python is required')
    pid = args.pid if args.pid is not None else current_pid()
    cached_path = args.profile or args.outdir / 'session-profile.json'
    cached = None
    if cached_path.exists():
        try:
            cached = json.loads(cached_path.read_text(encoding='utf-8-sig'))
        except (OSError, ValueError):
            pass  # An unreadable cache never supplies pointers.
    require_stopped(pid)
    with LiveGame(pid) as game:  # Exact executable hash, birth, RTTI and instruction guards.
        result, method, invalid_cache = fresh_profile(game, cached)
        fields, originals = boss_fields(result)
        charge_fields(game, result, fields)
        validate_fields(game, result, fields, originals)
        require_stopped(pid)
    boss = dict(session=result['session'], **fields, originals=originals, config_tag=config_tag(fields, originals),
                scope='Current process and encounter only')
    atomic_text(args.outdir / 'session-profile.json', json.dumps(result, indent=2))
    atomic_text(args.outdir / 'native/boss_session.h', session_header(fields, originals))
    atomic_text(args.outdir / 'boss-session.json', json.dumps(boss, indent=2))
    print(json.dumps(dict(prepared=True, pid=pid, creation_filetime=result['session']['creation_filetime'],
                          method=method, invalid_cache=invalid_cache, outdir=str(args.outdir.resolve()),
                          player=hex(fields['player']), source=hex(fields['source_actor']),
                          game_modified=False, calibration_modified=False)))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, StopIteration, struct.error) as error:
        print(json.dumps(dict(status='error', stage='read_only_preparation', message=str(error))), file=sys.stderr)
        raise SystemExit(1)
