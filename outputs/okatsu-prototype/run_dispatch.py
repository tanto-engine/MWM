# Continuous LB+Circle boss gestures, with legacy one-shot player probes.
#
# The command mapping carries intent only. The native hook validates and forwards
# the replacement on an existing game-thread action call. No remote attack calls.
# TODO: Compare input sampling, gesture decision, dispatch and first motion
# timestamps separately before changing Charged Rush startup or polling cadence.
import argparse
import ctypes as C
from ctypes import wintypes as W
import json
import math
import os
from pathlib import Path
import struct
import sys
import time

from capture_native import run, loader_report, CommandFailure
from calibrate_controller import CalibratedChord
from circle_gesture import CircleGesture
from engine_config import atomic_json, read_json, validate_preset, binding_for_preset
from process_support import process_identity
from trace_reader import Trace, CAPACITY
from game_controller import GameController, game_binding
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'boss-probe'))
from boss_probe import LiveGame, U64, I32, U32
from controller_reader import ControllerReader, WinMMBackend, XInputBackend

HERE = Path(os.environ.get('NIOH_RUNTIME_HOME', Path(__file__).resolve().parent))
CODE = Path(__file__).resolve().parent
CONTROL = struct.Struct('<IIIIqQiiqqii')
COMMAND = struct.Struct('<qqqq10QIiII3Qq')
assert CONTROL.size == 64 and COMMAND.size == 160


class DispatchIntent:
    # Cancel an expired/released intent permanently; only a fresh gate edge arms.
    def __init__(self, frequency):
        # Initialize the legacy one-shot chord lease on the QPC clock.
        # Start with no edge, held state or consumed dispatch.
        # Only a fresh logical chord may create an intent.
        self.frequency = frequency
        self.chord_sequence = self.edge = self.expires = 0
        self.held = self.lt_pressed = self.shot_used = False

    def cancel(self, reset_lt=False):
        # Clear the active edge and its expiry.
        # Optionally discard trigger hysteresis on device or context loss.
        # A released or expired command must not rearm itself.
        self.edge = self.expires = 0
        self.held = False
        if reset_lt:
            self.lt_pressed = False

    def process(self, logical, now):
        # Translate calibrated input into a bounded one-shot lease.
        # Use trigger hysteresis and require a fresh chord candidate.
        # Cancel immediately on disconnection or invalid gameplay context.
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
        # Consume the current intent after native dispatch feedback.
        # Mark one-shot probes spent while allowing repeat mode to rearm.
        # Prevent the same held edge from producing duplicate requests.
        self.shot_used = not repeat
        self.cancel()

    def fields(self, now):
        # Serialize intent timing and current held state for shared memory.
        # Compute armed state against the current clock and expiry.
        # Native dispatch receives a time-limited request rather than an attack call.
        return dict(heartbeat=now, edge=self.edge, expires=self.expires,
                    chord_sequence=self.chord_sequence,
                    armed=bool(not self.shot_used and self.held and 0 < self.edge <= now < self.expires),
                    held=self.held)


class CommandMap:
    def __init__(self, pid, prefix='NiohDispatchCommand_v1', tag=None):
        # Open the command mapping named for a process and configuration.
        # Validate its schema and release handles if initialization fails.
        # Prevent a publisher from attaching to an incompatible native session.
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
        # Decode the native feedback header from shared memory.
        # Require the expected magic, sizes and positive clock frequency.
        # Expose dispatch generation and gameplay context to the publisher.
        values = CONTROL.unpack(C.string_at(self.address, CONTROL.size))
        if values[:3] != (0x3144494E, 1, 160) or values[4] <= 0:
            raise ValueError('Dispatch command protocol mismatch')
        return dict(frequency=values[4], generation=values[5], enabled=values[6], status=values[7],
                    consumed_sequence=values[8], dispatch_count=values[9], last_reason=values[10],
                    voice_suppressed_count=values[11], context_flags=values[3] & 65535,
                    context_epoch=values[3] >> 16)

    def qpc(self):
        # Read Windows' high-resolution counter for command timestamps.
        # Use the same clock as the native dispatcher.
        # Keep gesture age and heartbeat expiry directly comparable.
        value = C.c_int64()
        if not self.kernel.QueryPerformanceCounter(C.byref(value)):
            raise C.WinError(C.get_last_error())
        return value.value

    def publish(self, config, *, heartbeat, edge, expires, chord_sequence, armed, held, latched=0, variant=0, context_epoch=0):
        # Write one selected move and its input lease into shared memory.
        # Commit matching sequence markers after the payload copy.
        # The native reader rejects partial publication without blocking the game thread.
        self.sequence += 1
        selected = config['imports'][variant] if 'imports' in config else config.get('charged', config) if variant else config
        body = COMMAND.pack(self.sequence, heartbeat, edge, expires, chord_sequence,
                            config['generation'], config['player'], config['owner'], config['vtable'],
                            *config['banks'], selected['descriptor'], selected['payload'], selected['key'],
                            selected['motion'], int(armed), int(held), latched, variant, context_epoch, self.sequence)
        address = self.address + CONTROL.size
        # Single publisher, aligned 64-bit stores on Windows x64. Native reads
        # both markers with interlocked barriers and never waits on the writer.
        C.c_int64.from_address(address).value = 0
        C.c_int64.from_address(address + 152).value = 0
        C.memmove(address + 8, body[8:152], 144)
        C.c_int64.from_address(address + 152).value = self.sequence
        C.c_int64.from_address(address).value = self.sequence

    def close(self):
        # Unmap the command view and release its Windows handle.
        # Clear both references so repeated cleanup is harmless.
        # Do not leave publisher resources open after failed attachment.
        if self.address:
            self.kernel.UnmapViewOfFile(self.address)
            self.address = None
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def prepare(game, profile, key, boss=False):
    # Resolve a requested action from a process-matched resource profile.
    # Require verified motion and timing dependencies before building command fields.
    # Revalidate the live actor and descriptor before publishing anything.
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
    # Cross-check the session configuration against inspected resource identities.
    # Compare action, clip and timing pointers with the selected source.
    # Reject stale configuration before enabling the dispatcher.
    source, player = profile['source'], profile['player']
    expected = dict(player=config['player'], player_owner=config['owner'], vtable=config['vtable'],
                    source_descriptor=config['descriptor'], source_payload=config['payload'],
                    source_action_resource=int(source['action_resource'], 0), source_timing_resource=int(source['timing_resource'], 0),
                    source_bank=int(source['action_resolution']['bank_address'], 0),
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
    # Observe player slots, playback resources and optional Ki telemetry.
    # Verify owner and resource identity without repairing memory externally.
    # Use the same evidence for activation checks and restoration reporting.
    # Read actual consumed clip/timing resources; never repair them externally.
    game.begin_sample()
    _, player_state = game.snapshot(boss['player'])
    if int(player_state['owner_like'], 0) != boss['player_owner']:
        raise ValueError('Player resource owner changed')
    owner = boss['player_owner']
    if (U64(game.bytes(owner+0x38,8),0) != boss['player_motion']
            or U64(game.bytes(owner+0x68,8),0) != boss['player_timing']):
        raise ValueError('Player motion/timing component changed')
    base = int(game.identity['module_base'], 0)
    groups = {(boss['source_action_resource'], boss['source_timing_resource'], boss['source_bank'],
               boss['source_motion_bank'], boss['source_timing_wrapper'])}
    groups.update(tuple(adapter[field] for field in ('action_resource', 'timing_resource', 'bank', 'motion_bank', 'timing_wrapper'))
                  for adapter in boss['adapters'] if adapter is not None)
    for actions, timing_resource, bank, motion_bank, timing_wrapper in groups:
        for resource, vtable, offset, value in (
            (actions, base+0x13C7970, 0x468, bank),
            (timing_resource, base+0x12C5408, 0x468, timing_wrapper),
            (motion_bank, base+0x13C8FA0, 0, base+0x13C8FA0)):
            if U64(game.bytes(resource,8),0) != vtable or U64(game.bytes(resource+offset,8),0) != value:
                raise ValueError('Engine resource ownership changed')
    addresses = [boss['player_motion']+8, boss['player_motion']+0x28,
                 boss['player_timing']+0x10, boss['player_timing']+0x28]
    borrowed = [[motion]*2 + [timing]*2 for _, _, _, motion, timing in groups]
    slots = [U64(game.bytes(address, 8), 0) for address in addresses]
    if require_originals and slots != boss['originals']:
        raise ValueError('Player resource slots have not all been restored')
    # Restoration may mix originals with one borrowed group temporarily. Mixing
    # different imported motion/timing groups cannot represent one coherent action.
    if not any(all(value in (original, replacement) for value, original, replacement in zip(slots, boss['originals'], group))
               for group in borrowed):
        raise ValueError('Unexpected player resource slot value or mixed group')
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
    # Reopen the original process for a restoration snapshot.
    # Reject a different process lifetime even if the PID matches.
    # Report retained replacement slots instead of assuming Stop restored them.
    with LiveGame(session['pid']) as game:
        if game.identity != session:
            raise ValueError('Cannot verify restoration in a different game process')
        # Return all state even if expected slots are still borrowed, for evidence.
        return boss_snapshot(game, boss)


def validate(game, config, allow_bank_change=False):
    # Recheck player ownership and selected action bytes during dispatch.
    # Permit bank changes only when the repeat-mode lifecycle policy owns recovery.
    # Raise on identity loss so the supervisor reacquires the session.
    if not game.alive():
        raise ValueError('Game exited')
    game.begin_sample()
    raw, state = game.snapshot(config['player'])
    if U64(raw, 0) != config['vtable'] or int(state['owner_like'], 0) != config['owner']:
        raise ValueError('Player identity changed; reacquisition required')
    banks = [U64(raw, 0x70 + i*8) for i in range(3)]
    if banks != config['banks'] and not allow_bank_change:
        raise ValueError('Player banks changed before attachment')
    desc = game.bytes(config['descriptor'], 0x44)
    if U32(desc, 0) != config['key'] or not desc[0x40] or U64(desc, 0x20) != config['payload']:
        raise ValueError('Desired action record changed')
    if I32(game.bytes(config['payload'] + 0x20, 4), 0) != config['motion']:
        raise ValueError('Desired action motion changed')
    return banks


def main():
    # Publish controller intent to the guarded game-thread dispatcher.
    # Track lifecycle epochs, binding changes, resource state and native feedback.
    # Disarm and wait for native recovery before releasing an active session.
    parser = argparse.ArgumentParser(description='Run the skill engine with the saved controller mapping')
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--calibration', type=Path, default=HERE / 'controller-calibration.json')
    parser.add_argument('--binding', type=Path, default=HERE / 'controller-binding.json')
    parser.add_argument('--dll', type=Path)
    parser.add_argument('--key', type=lambda s: (
        # Parse an explicit CLI address or action key.
        # Accept decimal and prefixed hexadecimal through Python integer parsing.
        # Reject malformed values before the command can attach to a process.
        int(s, 0)))
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
    if args.repeat:
        preset=validate_preset(read_json(args.binding))
        if profile.get('preset',preset) != preset:
            raise ValueError('Preset changed during preparation; reacquisition required')
        calibration, runtime_binding = game_binding(calibration, binding_for_preset(calibration,preset))
    gate = None if args.repeat else CalibratedChord(calibration)
    reader = None if args.repeat else ControllerReader(backends=[{'winmm': WinMMBackend, 'xinput': XInputBackend}[calibration['device']['backend']]()])
    args.outdir.mkdir(parents=True, exist_ok=False)
    session = profile['session']
    base = [CODE / 'native_loader.py', '--pid', session['pid'], '--creation-filetime', session['creation_filetime'],
            '--dll', args.dll.resolve()]
    status = dict(start_attempted=False, start_completed=False, stop_attempted=False, stop_completed=False,
                  dispatch_count=0, recovery_seconds=5 if boss else 3, repeat=args.repeat, errors=[])
    command = trace = config = None
    start_report = None
    start_attempted = False
    try:
        with LiveGame(session['pid']) as game:
            config = prepare(game, profile, args.key, boss=args.boss)
            if args.repeat:
                config['charged'] = dict(descriptor=boss['charge_descriptor'], payload=boss['charge_payload'], key=0xC66, motion=1230)
                config['imports'] = boss['imports']
            if boss:
                validate_boss_profile(config, profile, boss)
                boss_snapshot(game, boss, require_originals=True)
            start_attempted = True
            status['start_attempted'] = True
            start_command = [*base, '--session-config', HERE / 'boss-session.json'] if args.repeat else base
            start_report = loader_report(run(start_command, args.outdir, 'start'))
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
            if args.repeat:
                controller = GameController(trace, calibration)
                reader = ControllerReader(backends=[controller], rescan_seconds=.1)
            sequence = trace_header['written'] + 1
            frequency = control['frequency']
            started = command.qpc()
            deadline = started + int(args.seconds * frequency) if args.seconds else None
            intent = CircleGesture(calibration, runtime_binding, frequency, boss['string_variant']) if args.repeat else DispatchIntent(frequency)
            next_check = started
            last_resource_state = None
            last_gesture = 0
            last_feedback = None
            next_telemetry = started
            next_resources = started
            live_input = {}
            last_input_event = None
            context_epoch = control.get('context_epoch', 0)
            context_valid = not args.repeat
            changed_banks = None
            changed_since = started
            binding_stamp = args.binding.stat().st_mtime_ns if args.repeat else None
            (args.outdir / 'ready.json').write_text(json.dumps(dict(pid=session['pid'], enabled=True)))
            print('Sword preset active. Release controls to arm configured gestures.' if args.repeat else
                  'One-shot LB+LT replacement active. Release both, then press and hold together once.', flush=True)
            with (args.outdir / 'events.jsonl').open('x', encoding='utf8') as output:
                def emit(event):
                    # Append one publisher or native event to the session evidence stream.
                    # Retain its original timing fields without converting clocks.
                    # Allow later latency and lifecycle analysis from the same trace.
                    output.write(json.dumps(event) + '\n')
                emit(dict(kind='session', **session, desired_key=args.key, config=config, qpc_frequency=frequency))
                while (deadline is None or command.qpc() < deadline) and not (args.stop_file and args.stop_file.exists()):
                    begin = command.qpc()
                    if args.repeat:
                        control = command.control()
                        flags = control['context_flags']
                        playable = flags & 11 == 11 and bool(flags & (4 | 16))
                        if control['context_epoch'] != context_epoch or playable != context_valid:
                            intent.reset()
                            context_epoch = control['context_epoch']
                            emit(dict(kind='gameplay_context', flags=flags, epoch=context_epoch, observed_qpc=begin))
                            if playable and last_input_event:
                                intent.process(dict(last_input_event, edge_basis='unknown'), begin)
                        context_valid = playable
                    for event in reader.poll():
                        if event.get('kind') == 'input' and (event.get('backend'), event.get('slot')) == (calibration['device']['backend'], calibration['device']['slot']):
                            last_input_event = event
                        emit(dict(**event, poll_qpc_begin=begin, poll_qpc_end=command.qpc()))
                        logical = intent.process(event, event.get('sample_qpc', command.qpc()), context_valid=context_valid) if args.repeat else gate.process(event, context_valid=True)
                        if logical:
                            live_input = logical
                            logical_qpc = command.qpc()
                            emit(dict(**logical, logical_qpc=logical_qpc))
                            if not args.repeat:
                                intent.process(logical, logical_qpc)
                    now = command.qpc()
                    if now >= next_check:
                        banks = validate(game, config, allow_bank_change=args.repeat)
                        if args.repeat:
                            # A transient alternate bank keeps the current session.
                            # A stable, neutral, advancing replacement is reprofiled
                            # through the existing guarded startup, never adopted here.
                            changed = not (flags & 2 and flags & (4 | 16))
                            if changed and flags & 41 == 41 and not flags & 16:
                                signature = tuple(banks)
                                if signature != changed_banks:
                                    changed_banks, changed_since = signature, now
                                elif now - changed_since >= frequency:
                                    raise ValueError('Stable player configuration changed; reacquisition required')
                            else:
                                changed_banks = None
                            if flags and not flags & 1:
                                boss_snapshot(game, boss)
                        if args.repeat and args.binding.stat().st_mtime_ns != binding_stamp:
                            if validate_preset(read_json(args.binding)) != preset:
                                raise ValueError('Sword preset changed; reacquisition required')
                            binding_stamp = args.binding.stat().st_mtime_ns
                        next_check = now + int(.1 * frequency)
                    fields = intent.fields(now)
                    if fields['chord_sequence'] != last_gesture:
                        emit(dict(kind='gesture_intent', observed_qpc=now,
                                  action=boss['imports'][fields['variant']]['name'] if args.repeat else 'preview', **fields))
                        last_gesture = fields['chord_sequence']
                    command.publish(config, **fields, context_epoch=context_epoch)
                    if boss and (not args.repeat or context_valid) and now >= next_resources:
                        resource_state = boss_snapshot(game, boss)
                        if resource_state != last_resource_state:
                            emit(dict(**resource_state, observed_qpc=command.qpc()))
                            last_resource_state = resource_state
                        next_resources = now + int(.02 * frequency)
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
                                record['action_name'] = next((move['name'] for move in boss['imports'] if move['key'] == record['forwarded_key']), None)
                            if record['final_exact_match'] and record['valid_fields'] & (1 << 18):
                                record['decision_qpc'] = int(record['context'], 0)
                                record['context'] = '0x0'
                                record['decision_to_dispatch_ms'] = (record['qpc']-record['decision_qpc'])*1000/frequency
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
                        command.publish(config, **intent.fields(now), context_epoch=context_epoch)
                        # Even a dispatch near the listen deadline gets recovery.
                        if args.repeat:
                            print(f"Move triggered ({control['dispatch_count']}); release the chord to rearm.", flush=True)
                        else:
                            deadline = now + int((5 if boss else 3) * frequency)
                            print('One replacement attempted; allowing native recovery, then stopping.', flush=True)
                    status.update(dispatch_count=control['dispatch_count'], native_control=control)
                    if args.repeat and now >= next_telemetry:
                        atomic_json(args.outdir / 'live.json', dict(state=('enabled' if intent.connected else 'waiting_for_input') if context_valid else 'gameplay_suspended', input=live_input,
                            controller=controller.detection, buttons=last_input_event['button_labels'] if last_input_event and intent.connected else [],
                            input_transport='game_xinput',
                            dispatch_count=control['dispatch_count'], native_control=control,
                            resources=last_resource_state, updated_at=time.time()))
                        next_telemetry = now + int(.1 * frequency)
                    output.flush()
                    time.sleep(.002 if args.repeat else .01)
                if boss:
                    status['final_resources'] = boss_snapshot(game, boss)
    except Exception as error:
        if isinstance(error, CommandFailure) and error.name == 'start':
            start_report = error.report
        status['errors'].append(str(error))
    finally:
        # Cleanup attempts are independent: a mapping error must not skip native
        # Stop. Accumulate failures for the final nonzero exit instead of hiding
        # them or abandoning a move that still owns temporary player slots.
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
                        if args.repeat and error.report and error.report.get('result') == 170:
                            birth = process_identity(session['pid'])
                            if not birth or birth['publisher_start_filetime'] != str(session['creation_filetime']):
                                status.update(stop_completed=True, process_retired=True)
                                break
                            atomic_json(args.outdir / 'live.json', dict(state='waiting_for_recovery',
                                detail='Input is disarmed; waiting for native move recovery before reattachment.',
                                updated_at=time.time()))
                        elif not boss or not error.report or error.report.get('result') != 170 or time.perf_counter() >= stop_deadline:
                            raise
                        attempt += 1
                        status['stop_busy_retries'] = attempt
                        time.sleep(.25)
            except Exception as error:
                birth = process_identity(session['pid']) if args.repeat else None
                if args.repeat and (not birth or birth['publisher_start_filetime'] != str(session['creation_filetime'])):
                    status.update(stop_completed=True, process_retired=True)
                else:
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
