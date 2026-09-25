# Bounded input/native-action observation on the same Windows QPC clock.
#
# Does not write game memory or synthesize inputs. The passive hook must already
# be started by capture_native.py, which owns stopping it. Temporal proximity is
# evidence of timing, not proof that an OS input caused a particular action.
import argparse
import ctypes as C
from ctypes import wintypes as W
import json
from pathlib import Path
import sys
import time

from trace_reader import Trace, CAPACITY
from calibrate_controller import CalibratedChord
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'boss-probe'))
from boss_probe import LiveGame
from controller_reader import ControllerReader, WinMMBackend, XInputBackend


def player_identity_matches(record, actor, owner):
    # Match both actor and owner against a valid native record.
    # Require the native validity bit before trusting either pointer.
    # Avoid attributing another actor's actions to William after address reuse.
    return bool(record['valid_fields'] & 1 and int(record['actor'], 0) == actor
                and int(record['owner'], 0) == owner)


def main():
    # Record controller observations and native calls on the same QPC clock.
    # Revalidate player identity and report overwritten or racing trace slots.
    # Keep temporal association separate from proof of accepted game input.
    parser = argparse.ArgumentParser(description='Record controller inputs and native actions on one clock.')
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--creation-filetime', required=True)
    parser.add_argument('--player', type=lambda x: (
        # Parse an explicit CLI address or action key.
        # Accept decimal and prefixed hexadecimal through Python integer parsing.
        # Reject malformed values before the command can attach to a process.
        int(x, 0)), required=True)
    parser.add_argument('--owner', type=lambda x: (
        # Parse an explicit CLI address or action key.
        # Accept decimal and prefixed hexadecimal through Python integer parsing.
        # Reject malformed values before the command can attach to a process.
        int(x, 0)), required=True)
    parser.add_argument('--calibration', type=Path, required=True)
    parser.add_argument('--seconds', type=float, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if not 0 < args.seconds <= 60:
        parser.error('Duration must be 0..60 seconds')
    calibration = json.loads(args.calibration.read_text())
    chord = CalibratedChord(calibration)
    backend = {'winmm': WinMMBackend, 'xinput': XInputBackend}[calibration['device']['backend']]()
    reader = ControllerReader(backends=[backend])
    kernel = C.WinDLL('kernel32', use_last_error=True)
    kernel.QueryPerformanceCounter.argtypes = [C.POINTER(C.c_int64)]
    kernel.QueryPerformanceCounter.restype = W.BOOL
    kernel.QueryPerformanceFrequency.argtypes = [C.POINTER(C.c_int64)]
    kernel.QueryPerformanceFrequency.restype = W.BOOL
    frequency = C.c_int64()
    if not kernel.QueryPerformanceFrequency(C.byref(frequency)):
        raise C.WinError(C.get_last_error())

    def qpc():
        # Read the native counter used by both input and action evidence.
        # Raise when the OS cannot provide a timestamp.
        # An invented timestamp would invalidate latency comparisons.
        value = C.c_int64()
        if not kernel.QueryPerformanceCounter(C.byref(value)):
            raise C.WinError(C.get_last_error())
        return value.value

    with LiveGame(args.pid) as game:
        if game.identity['creation_filetime'] != args.creation_filetime:
            raise ValueError('Process birth mismatch')

        def validate():
            # Verify the original process still owns the selected player object.
            # Refresh region checks before reading its owner.
            # End capture rather than silently following a replacement actor.
            if not game.alive():
                raise ValueError('Game process exited')
            game.begin_sample()
            _, state = game.snapshot(args.player)
            if int(state['owner_like'], 0) != args.owner:
                raise ValueError('Player object was replaced; capture ended')
            return qpc()

        identity_checked_qpc = validate()
        trace = Trace(args.pid)
        try:
            header = trace.header()
            if not header['enabled'] or header['frequency'] != frequency.value:
                raise ValueError('Observer inactive or QPC frequency mismatch')
            # Retained events from an earlier capture are deliberately excluded.
            next_sequence = header['written'] + 1
            first_dropped = header['dropped']
            counts = dict(actions=0, player_actions=0, chord_candidates=0, overwritten=0, slot_races=0)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            with args.out.open('x', encoding='utf8') as output:
                def emit(value):
                    # Append a complete timestamped evidence object as one JSON line.
                    # Preserve the producer's timing and identity fields.
                    # The final summary shares this stream with all preceding observations.
                    output.write(json.dumps(value) + '\n')
                started = qpc()
                emit(dict(kind='session', **game.identity, frequency=frequency.value,
                          started_qpc=started, player=hex(args.player), owner=hex(args.owner),
                          calibration=calibration, identity_check_period_seconds=0.1,
                          scope='passive; context_valid means last checked actor/owner identity only, not gameplay state'))
                last_validation = identity_checked_qpc
                failure = None
                print('Input and native-action capture active.', flush=True)
                try:
                    while qpc() - started < args.seconds * frequency.value:
                        before_poll = qpc()
                        events = reader.poll()
                        after_poll = qpc()
                        if after_poll - last_validation >= frequency.value / 10:
                            last_validation = validate()
                        for event in events:
                            emit(dict(**event, poll_qpc_begin=before_poll, poll_qpc_end=after_poll))
                            logical = chord.process(event, context_valid=True)
                            if logical:
                                emit(dict(**logical, poll_qpc_begin=before_poll, poll_qpc_end=after_poll,
                                          identity_checked_qpc=last_validation))
                                counts['chord_candidates'] += bool(logical.get('chord_candidate'))
                        header = trace.header()
                        if not header['enabled']:
                            raise ValueError('Observer stopped during capture')
                        oldest = max(1, header['written'] - CAPACITY + 1)
                        if next_sequence < oldest:
                            counts['overwritten'] += oldest - next_sequence
                            emit(dict(kind='overwritten', first=next_sequence, next=oldest))
                            next_sequence = oldest
                        for sequence in range(next_sequence, header['written'] + 1):
                            record = trace.record(sequence)
                            if record is None:
                                counts['slot_races'] += 1
                                emit(dict(kind='slot_race', sequence=sequence))
                            else:
                                matched = player_identity_matches(record, args.player, args.owner)
                                emit(dict(kind='action_call', **record, player_identity_match=matched,
                                          entry_before_session=record['qpc'] < started))
                                counts['actions'] += 1
                                counts['player_actions'] += matched
                            next_sequence = sequence + 1
                        output.flush()
                        time.sleep(.01)
                except Exception as error:
                    failure = str(error)
                    raise
                finally:
                    summary = dict(kind='summary', **counts, error=failure,
                                   elapsed_seconds=(qpc() - started) / frequency.value,
                                   dropped=trace.header()['dropped'] - first_dropped)
                    emit(summary)
                    print(json.dumps(summary), flush=True)
        finally:
            trace.close()


if __name__ == '__main__':
    main()
