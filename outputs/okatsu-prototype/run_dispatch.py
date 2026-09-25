"""Continuous LB+Circle boss gestures, with legacy one-shot player probes.

The command mapping carries intent only. The native hook validates and forwards
the replacement on an existing game-thread action call. No remote attack calls.
"""
import argparse
import ctypes as C
from ctypes import wintypes as W
import json
import math
from pathlib import Path
import struct
import sys
import time

from capture_native import run, loader_report, CommandFailure
from calibrate_controller import CalibratedChord
from circle_gesture import CircleGesture
from trace_reader import Trace, CAPACITY
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'boss-probe'))
from boss_probe import LiveGame, U64, I32, U32
from controller_reader import ControllerReader, WinMMBackend, XInputBackend

HERE = Path(__file__).resolve().parent
CONTROL = struct.Struct('<IIIIqQiiqqii')
COMMAND = struct.Struct('<qqqq10QIiII3Qq')
assert CONTROL.size == 64 and COMMAND.size == 160


class DispatchIntent:
    """Cancel an expired/released intent permanently; only a fresh gate edge arms."""
    def __init__(self, frequency):
        self.frequency = frequency
        self.chord_sequence = self.edge = self.expires = 0
        self.held = self.lt_pressed = self.shot_used = False

    def cancel(self, reset_lt=False):
        self.edge = self.expires = 0
        self.held = False
        if reset_lt:
            self.lt_pressed = False

    def process(self, logical, now):
        if logical['kind'] != 'logical_input':
            # A reconnect/device match resets the gate, even when accepted.
            self.cancel(reset_lt=True)
            return
        lt = logical.get('lt')
        if (not logical.get('connected') or not logical.get('context_valid')
                or not isinstance(lt, (int, float)) or isinstance(lt, bool)
                or not math.isfinite(lt) or not 0 <= lt <= 1):
            self.cancel(reset_lt=True)
            return
        if lt >= .6:
            self.lt_pressed = True
        elif lt <= .4:
            self.lt_pressed = False
        self.held = bool(logical.get('lb') and self.lt_pressed)
        if not self.held:
            self.cancel()
        elif not self.shot_used and logical.get('chord_candidate'):
            self.chord_sequence += 1
            self.edge = now
            self.expires = now + int(1.2 * self.frequency)

    def dispatched(self, repeat=False):
        self.shot_used = not repeat
        self.cancel()

    def fields(self, now):
        return dict(heartbeat=now, edge=self.edge, expires=self.expires,
                    chord_sequence=self.chord_sequence,
                    armed=bool(not self.shot_used and self.held and 0 < self.edge <= now < self.expires),
                    held=self.held)


class CommandMap:
    def __init__(self, pid, prefix='NiohDispatchCommand_v1', tag=None):
        if prefix not in ('NiohDispatchCommand_v1', 'NiohBossCommand_v1', 'NiohBossRepeatCommand_v1', 'NiohBossRepeatCommand_v2'):
            raise ValueError('Unknown command mapping prefix')
        if prefix.endswith('_v2') and (not isinstance(tag, str) or len(tag) != 16 or any(c not in '0123456789abcdef' for c in tag)):
            raise ValueError('Repeat v2 requires a configuration tag')
        self.kernel = C.WinDLL('kernel32', use_last_error=True)
        self.kernel.OpenFileMappingW.argtypes = [W.DWORD, W.BOOL, W.LPCWSTR]
        self.kernel.OpenFileMappingW.restype = W.HANDLE
        self.kernel.MapViewOfFile.argtypes = [W.HANDLE, W.DWORD, W.DWORD, W.DWORD, C.c_size_t]
        self.kernel.MapViewOfFile.restype = C.c_void_p
        self.kernel.UnmapViewOfFile.argtypes = [C.c_void_p]
        self.kernel.UnmapViewOfFile.restype = W.BOOL
        self.kernel.CloseHandle.argtypes = [W.HANDLE]
        self.kernel.CloseHandle.restype = W.BOOL
        self.kernel.QueryPerformanceCounter.argtypes = [C.POINTER(C.c_int64)]
        self.kernel.QueryPerformanceCounter.restype = W.BOOL
        self.handle = self.kernel.OpenFileMappingW(6, False, f'Local\\{prefix}_{pid}' + (f'_{tag}' if prefix.endswith('_v2') else ''))
        if not self.handle:
            raise C.WinError(C.get_last_error())
        self.address = self.kernel.MapViewOfFile(self.handle, 6, 0, 0, 224)
        if not self.address:
            error = C.get_last_error()
            self.kernel.CloseHandle(self.handle)
            self.handle = None
            raise C.WinError(error)
        self.sequence = 0
        try:
            self.control()
        except BaseException:
            self.close()
            raise

    def control(self):
        values = CONTROL.unpack(C.string_at(self.address, CONTROL.size))
        if values[:3] != (0x3144494E, 1, 160) or values[4] <= 0:
            raise ValueError('Dispatch command protocol mismatch')
        return dict(frequency=values[4], generation=values[5], enabled=values[6], status=values[7],
                    consumed_sequence=values[8], dispatch_count=values[9], last_reason=values[10],
                    voice_suppressed_count=values[11])

    def qpc(self):
        value = C.c_int64()
        if not self.kernel.QueryPerformanceCounter(C.byref(value)):
            raise C.WinError(C.get_last_error())
        return value.value

    def publish(self, config, *, heartbeat, edge, expires, chord_sequence, armed, held, latched=0, variant=0):
        self.sequence += 1
        selected = config.get('charged', config) if variant else config
        body = COMMAND.pack(self.sequence, heartbeat, edge, expires, chord_sequence,
                            config['generation'], config['player'], config['owner'], config['vtable'],
                            *config['banks'], selected['descriptor'], selected['payload'], selected['key'],
                            selected['motion'], int(armed), int(held), latched, variant, 0, self.sequence)
        address = self.address + CONTROL.size
        # Single publisher, aligned 64-bit stores on Windows x64. Native reads
        # both markers with interlocked barriers and never waits on the writer.
        C.c_int64.from_address(address).value = 0
        C.c_int64.from_address(address + 152).value = 0
        C.memmove(address + 8, body[8:152], 144)
        C.c_int64.from_address(address + 152).value = self.sequence
        C.c_int64.from_address(address).value = self.sequence

    def close(self):
        if self.address:
            self.kernel.UnmapViewOfFile(self.address)
            self.address = None
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def prepare(game, profile, key, boss=False):
    if game.identity != profile['session']:
        raise ValueError('Profile does not match the live process')
    player = profile['player']
    matches = ([dict(action_key=key, resolution=profile['source']['action_resolution'],
                     motion_key=profile['source']['motion_key'], resources=profile['source']['resources'])] if boss else
               [a for a in player['target_actions'] if a['action_key'] == key and a.get('resolution')])
    if len(matches) != 1:
        raise ValueError('Desired player action is not uniquely profiled')
    target = matches[0]
    for kind in ('motion', 'timing'):
        if not target.get('resources', {}).get(kind, {}).get('present_slots'):
            raise ValueError(f'Desired player action has no verified loaded {kind} resource')
    entry = target['resolution']
    config = dict(player=int(player['actor'], 0), owner=int(player['owner'], 0),
                  vtable=int(game.identity['vtable'], 0), banks=[int(b, 0) for b in player['action_banks']],
                  descriptor=int(entry['descriptor'], 0), payload=int(entry['payload'], 0),
                  key=key, motion=target['motion_key'])
    validate(game, config)
    return config


def validate_boss_profile(config, profile, boss):
    source, player = profile['source'], profile['player']
    expected = dict(player=config['player'], player_owner=config['owner'], vtable=config['vtable'],
                    source_descriptor=config['descriptor'], source_payload=config['payload'],
                    source_actor=int(source['actor'], 0), source_owner=int(source['owner'], 0),
                    source_bank=int(source['action_resolution']['bank_address'], 0),
                    source_motion=int(source['resources']['motion_object'], 0),
                    source_timing=int(source['resources']['timing_object'], 0),
                    player_motion=int(player['resources']['motion_object'], 0),
                    player_timing=int(player['resources']['timing_object'], 0))
    if boss['session'] != profile['session'] or any(boss[name] != value for name, value in expected.items()):
        raise ValueError('Boss preview constants disagree with selected profile identities')
    if config['key'] != source['action_resolution']['key_u32'] or config['motion'] != 1220:
        raise ValueError('Boss preview requires the researched C64/motion1220 source')
    motion = source['resources']['motion']['banks']
    timing = source['resources']['timing']['banks']
    if not any(r.get('presence') == 'present' and int(r['bank'], 0) == boss['source_motion_bank']
               and int(r['clip'], 0) == boss['source_clip'] for r in motion):
        raise ValueError('Boss preview source clip disagrees with profiled lookup')
    if not any(r.get('presence') == 'present' and int(r['wrapper'], 0) == boss['source_timing_wrapper']
               and int(r['record'], 0) == boss['source_timing_record'] for r in timing):
        raise ValueError('Boss preview source timing disagrees with profiled lookup')


def boss_snapshot(game, boss, require_originals=False):
    """Read actual consumed clip/timing resources; never repair them externally."""
    game.begin_sample()
    raw, state = game.snapshot(boss['source_actor'])
    if int(state['owner_like'], 0) != boss['source_owner'] or U64(raw, 0x78) != boss['source_bank']:
        raise ValueError('Okatsu resource owner changed')
    _, player_state = game.snapshot(boss['player'])
    if int(player_state['owner_like'], 0) != boss['player_owner']:
        raise ValueError('Player resource owner changed')
    for owner, motion, timing in [(boss['player_owner'], boss['player_motion'], boss['player_timing']),
                                  (boss['source_owner'], boss['source_motion'], boss['source_timing'])]:
        if U64(game.bytes(owner+0x38, 8), 0) != motion or U64(game.bytes(owner+0x68, 8), 0) != timing:
            raise ValueError('Motion/timing component identity changed')
    if (U64(game.bytes(boss['source_motion']+8, 8), 0) != boss['source_motion_bank']
            or U64(game.bytes(boss['source_timing']+0x10, 8), 0) != boss['source_timing_wrapper']):
        raise ValueError('Source motion/timing resource changed')
    addresses = [boss['player_motion']+8, boss['player_motion']+0x28,
                 boss['player_timing']+0x10, boss['player_timing']+0x28]
    borrowed = [boss['source_motion_bank']]*2 + [boss['source_timing_wrapper']]*2
    slots = [U64(game.bytes(address, 8), 0) for address in addresses]
    if require_originals and slots != boss['originals']:
        raise ValueError('Player resource slots have not all been restored')
    if any(value not in (original, replacement) for value, original, replacement in zip(slots, boss['originals'], borrowed)):
        raise ValueError('Unexpected player resource slot value')
    motion = game.bytes(boss['player_motion'], 0xF8)
    playback = U64(game.bytes(boss['player_timing']+0x40, 8), 0)
    timing = game.bytes(playback, 0x60)
    clips = [U64(motion, offset) for offset in (0x58, 0x88, 0xB8)]
    ki = {}
    try:
        vitals = U64(game.bytes(boss['player_owner'] + 0x240, 8), 0)
        if vitals >= 0x10000:
            values = game.bytes(vitals + 0x40, 0x5C)
            ki = {name: struct.unpack_from('<f', values, offset-0x40)[0] for name, offset in (
                ('current', 0x40), ('recoverable_now', 0x74), ('recoverable_target', 0x78),
                ('fill_duration', 0x8C), ('fill_remaining', 0x90),
                ('hold_duration', 0x94), ('hold_remaining', 0x98))}
            ki['action_cost'] = struct.unpack('<f', game.bytes(boss['player'] + 0x7A0, 4))[0]
    except (OSError, ValueError):
        pass  # Optional telemetry never changes attack eligibility.
    return dict(kind='resource_state', slots=[hex(v) for v in slots],
                ki=ki,
                stance=I32(game.bytes(boss['player']+0x470, 4), 0),
                all_slots_original=slots == boss['originals'],
                current_clip=hex(clips[0]), previous_clips=[hex(v) for v in clips[1:]],
                motion_key=I32(motion, 0xEC), timing_record=hex(U64(timing, 0x20)),
                timing_key=U64(timing, 0x58),
                source_clip_current=clips[0] == boss['source_clip'],
                source_clip_retained=boss['source_clip'] in clips,
                leaping_clip_current=clips[0] == boss.get('charge_clip'),
                leaping_timing_current=U64(timing, 0x20) == boss.get('charge_timing_record'),
                source_timing_current=U64(timing, 0x20) == boss['source_timing_record'])


def verify_boss_after_stop(session, boss):
    with LiveGame(session['pid']) as game:
        if game.identity != session:
            raise ValueError('Cannot verify restoration in a different game process')
        # Return all state even if expected slots are still borrowed, for evidence.
        return boss_snapshot(game, boss)


def validate(game, config):
    if not game.alive():
        raise ValueError('Game exited')
    game.begin_sample()
    raw, state = game.snapshot(config['player'])
    if int(state['owner_like'], 0) != config['owner'] or [U64(raw, 0x70 + i*8) for i in range(3)] != config['banks']:
        raise ValueError('Player or weapon bank identity changed; test stopped')
    desc = game.bytes(config['descriptor'], 0x44)
    if U32(desc, 0) != config['key'] or not desc[0x40] or U64(desc, 0x20) != config['payload']:
        raise ValueError('Desired action record changed')
    if I32(game.bytes(config['payload'] + 0x20, 4), 0) != config['motion']:
        raise ValueError('Desired action motion changed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--calibration', type=Path, default=HERE / 'controller-calibration.json')
    parser.add_argument('--dll', type=Path)
    parser.add_argument('--key', type=lambda s: int(s, 0))
    parser.add_argument('--boss', action='store_true')
    parser.add_argument('--repeat', action='store_true', help='Keep boss move enabled until stop file or process/actor change')
    parser.add_argument('--stop-file', type=Path)
    parser.add_argument('--seconds', type=float, default=25)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    if args.repeat and not args.boss:
        parser.error('--repeat requires --boss')
    if args.repeat and args.stop_file is None:
        args.stop_file = HERE / 'stop.flag'
    if args.stop_file and args.stop_file.exists():
        parser.error('Stop signal is present. Use Start-Okatsu.ps1 to start a new play session.')
    if args.key is None:
        args.key = 0xC64 if args.boss else 0xCF0
    if args.dll is None:
        args.dll = HERE / ('native/build/boss_repeat.dll' if args.repeat else 'native/build/boss_preview.dll' if args.boss else 'native/build/dispatch.dll')
    duration_valid = (args.repeat and args.seconds == 0) or 0 < args.seconds <= 45
    if args.key not in ((0xC64,) if args.boss else (0xCF0, 0xD34)) or not duration_valid or C.sizeof(C.c_void_p) != 8:
        parser.error('Require x64, researched target (boss C64 or player CF0/D34), and duration 0..45 seconds')
    profile = json.loads(args.profile.read_text())
    boss = json.loads((HERE / 'boss-session.json').read_text()) if args.boss else None
    if boss and boss['session'] != profile['session']:
        raise ValueError('Boss preview was built for a different game process')
    calibration = json.loads(args.calibration.read_text())
    gate = None if args.repeat else CalibratedChord(calibration)
    reader = ControllerReader(backends=[{'winmm': WinMMBackend, 'xinput': XInputBackend}[calibration['device']['backend']]()])
    args.outdir.mkdir(parents=True, exist_ok=False)
    session = profile['session']
    base = [HERE / 'native_loader.py', '--pid', session['pid'], '--creation-filetime', session['creation_filetime'],
            '--dll', args.dll.resolve()]
    status = dict(start_completed=False, stop_attempted=False, stop_completed=False,
                  dispatch_count=0, recovery_seconds=5 if boss else 3, repeat=args.repeat, errors=[])
    command = trace = config = None
    start_report = None
    start_attempted = False
    try:
        with LiveGame(session['pid']) as game:
            config = prepare(game, profile, args.key, boss=args.boss)
            if args.repeat:
                config['charged'] = dict(descriptor=boss['charge_descriptor'], payload=boss['charge_payload'], key=0xC66, motion=1230)
            if boss:
                validate_boss_profile(config, profile, boss)
                boss_snapshot(game, boss, require_originals=True)
            start_attempted = True
            start_report = loader_report(run(base, args.outdir, 'start'))
            status['start_completed'] = True
            mapping_options = dict(tag=boss['config_tag']) if args.repeat else {}
            command = CommandMap(session['pid'], 'NiohBossRepeatCommand_v2' if args.repeat else 'NiohBossCommand_v1' if boss else 'NiohDispatchCommand_v1', **mapping_options)
            control = command.control()
            if not control['enabled'] or control['generation'] <= 0 or control['dispatch_count']:
                raise ValueError('Dispatcher did not start a fresh enabled one-shot generation')
            config['generation'] = control['generation']
            trace = Trace(session['pid'], 'NiohBossRepeatTrace_v2' if args.repeat else 'NiohBossTrace_v1' if boss else 'NiohDispatchTrace_v1', **mapping_options)
            trace_header = trace.header()
            if not trace_header['enabled'] or trace_header['frequency'] != control['frequency']:
                raise ValueError('Dispatch trace inactive or QPC frequency mismatch')
            sequence = trace_header['written'] + 1
            frequency = control['frequency']
            started = command.qpc()
            deadline = started + int(args.seconds * frequency) if args.seconds else None
            intent = CircleGesture(calibration, json.loads((HERE / 'controller-binding.json').read_text()), frequency) if args.repeat else DispatchIntent(frequency)
            next_check = started
            last_resource_state = None
            last_gesture = 0
            last_feedback = None
            (args.outdir / 'ready.json').write_text(json.dumps(dict(pid=session['pid'], enabled=True)))
            print('LB + Circle enabled: tap/release = Charged Rush; hold = Leaping Slash. Release Circle between uses.' if args.repeat else
                  'One-shot LB+LT replacement active. Release both, then press and hold together once.', flush=True)
            with (args.outdir / 'events.jsonl').open('x', encoding='utf8') as output:
                def emit(event):
                    output.write(json.dumps(event) + '\n')
                emit(dict(kind='session', **session, desired_key=args.key, config=config, qpc_frequency=frequency))
                while (deadline is None or command.qpc() < deadline) and not (args.stop_file and args.stop_file.exists()):
                    begin = command.qpc()
                    for event in reader.poll():
                        emit(dict(**event, poll_qpc_begin=begin, poll_qpc_end=command.qpc()))
                        logical = intent.process(event, command.qpc(), context_valid=True) if args.repeat else gate.process(event, context_valid=True)
                        if logical:
                            logical_qpc = command.qpc()
                            emit(dict(**logical, logical_qpc=logical_qpc))
                            if not args.repeat:
                                intent.process(logical, logical_qpc)
                    now = command.qpc()
                    if now >= next_check:
                        validate(game, config)
                        next_check = now + int(.1 * frequency)
                    fields = intent.fields(now)
                    if fields['chord_sequence'] != last_gesture:
                        emit(dict(kind='gesture_intent', observed_qpc=now,
                                  action='Leaping Slash' if fields.get('variant') else 'Charged Rush', **fields))
                        last_gesture = fields['chord_sequence']
                    command.publish(config, **fields)
                    if boss:
                        resource_state = boss_snapshot(game, boss)
                        if resource_state != last_resource_state:
                            emit(dict(**resource_state, observed_qpc=command.qpc()))
                            last_resource_state = resource_state
                    header = trace.header()
                    oldest = max(1, header['written'] - CAPACITY + 1)
                    if sequence < oldest:
                        emit(dict(kind='overwritten', first=sequence, next=oldest))
                        sequence = oldest
                    for number in range(sequence, header['written'] + 1):
                        record = trace.record(number)
                        if record:
                            record['forwarded_key'] = record.pop('reserved')
                            record['dispatch_reason'] = (record['valid_fields'] >> 8) & 255
                            record['substitution_intended'] = bool(record['valid_fields'] & (1 << 16))
                            record['final_exact_match'] = bool(record['valid_fields'] & (1 << 17))
                            if record['substitution_intended']:
                                record['action_name'] = {0xC64: 'Okatsu Charged Rush', 0xC66: 'Okatsu Leaping Slash'}.get(record['forwarded_key'])
                            emit(dict(kind='action_call', **record))
                        else:
                            emit(dict(kind='slot_race', sequence=number))
                        sequence = number + 1
                    control = command.control()
                    feedback = (control.get('last_reason'), control.get('voice_suppressed_count', 0))
                    if feedback != last_feedback:
                        emit(dict(kind='dispatch_feedback', observed_qpc=command.qpc(),
                                  reason=feedback[0], voice_suppressed_count=feedback[1]))
                        last_feedback = feedback
                    if not control['enabled'] or control['generation'] != config['generation']:
                        raise ValueError('Dispatcher stopped or restarted')
                    if control['dispatch_count'] > status['dispatch_count']:
                        intent.dispatched(repeat=args.repeat)
                        command.publish(config, **intent.fields(now))
                        # Even a dispatch near the listen deadline gets recovery.
                        if args.repeat:
                            print(f"Move triggered ({control['dispatch_count']}); release Circle to rearm.", flush=True)
                        else:
                            deadline = now + int((5 if boss else 3) * frequency)
                            print('One replacement attempted; allowing native recovery, then stopping.', flush=True)
                    status.update(dispatch_count=control['dispatch_count'], native_control=control)
                    output.flush()
                    time.sleep(.01)
                if boss:
                    status['final_resources'] = boss_snapshot(game, boss)
    except Exception as error:
        if isinstance(error, CommandFailure) and error.name == 'start':
            start_report = error.report
        status['errors'].append(str(error))
    finally:
        if command:
            try:
                if config and 'generation' in config:
                    command.publish(config, heartbeat=command.qpc(), edge=0, expires=0,
                                    chord_sequence=0, armed=False, held=False)
            except Exception as error:
                status['errors'].append('Disarm: ' + str(error))
            try:
                command.close()
            except Exception as error:
                status['errors'].append('Command mapping close: ' + str(error))
        if trace:
            try:
                trace.close()
            except Exception as error:
                status['errors'].append('Trace mapping close: ' + str(error))
        no_mutation = start_report is not None and start_report.get('mutation_started') is False
        if start_attempted and not no_mutation:
            status['stop_attempted'] = True
            try:
                stop_deadline = time.perf_counter() + 10
                attempt = 0
                while True:
                    try:
                        label = 'stop' if not attempt else f'stop-retry{attempt}'
                        status['stop_report'] = loader_report(run([*base, '--export', 'NiohResearchStop'], args.outdir, label))
                        status['stop_completed'] = True
                        break
                    except CommandFailure as error:
                        status['stop_report'] = error.report
                        # Native Stop disarms immediately but retains the hook
                        # while a boss move still needs game-thread restoration.
                        if not boss or not error.report or error.report.get('result') != 170 or time.perf_counter() >= stop_deadline:
                            raise
                        attempt += 1
                        status['stop_busy_retries'] = attempt
                        time.sleep(.25)
            except Exception as error:
                status['errors'].append('Stop: ' + str(error))
            if boss:
                try:
                    after_stop = verify_boss_after_stop(session, boss)
                    status['post_stop_resources'] = after_stop
                    status['post_stop_slots_restored'] = after_stop['all_slots_original']
                    if status['stop_completed'] and not after_stop['all_slots_original']:
                        status['errors'].append('Stop returned success but borrowed resource slots remain')
                except Exception as error:
                    status['post_stop_slots_restored'] = None
                    status['errors'].append('Post-Stop read verification: ' + str(error))
        status['start_report'] = start_report
        (args.outdir / 'status.json').write_text(json.dumps(status, indent=2))
    print(json.dumps(status, indent=2), flush=True)
    if status['errors']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
