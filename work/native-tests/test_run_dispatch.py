"""Owned-buffer and fully mocked orchestration tests; never opens Nioh."""
import contextlib
import ctypes as C
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'outputs/okatsu-prototype'))
import run_dispatch as dispatch

CONFIG = dict(generation=7, player=0x100000, owner=0x200000, vtable=0x300000,
              banks=[0x400000, 0x500000, 0x600000], descriptor=0x700000,
              payload=0x800000, key=0xCF0, motion=4100)


def logical(*, lb=True, lt=1.0, edge=False, connected=True):
    return dict(kind='logical_input', lb=lb, lt=lt, chord_candidate=edge,
                connected=connected, context_valid=True)


class DispatchTests(unittest.TestCase):
    def test_pack_layout_and_uncommitted_markers_during_body_copy(self):
        buffer = C.create_string_buffer(bytes([0xA5]) * 224, 224)
        command = dispatch.CommandMap.__new__(dispatch.CommandMap)
        command.address, command.sequence = C.addressof(buffer), 0
        real_copy = C.memmove
        observed = []
        def copying(address, body, length):
            begin = C.c_int64.from_address(command.address + 64).value
            end = C.c_int64.from_address(command.address + 64 + 152).value
            observed.append((begin, end, address-command.address, length))
            return real_copy(address, body, length)
        with patch.object(dispatch.C, 'memmove', side_effect=copying):
            command.publish(CONFIG, heartbeat=1000, edge=900, expires=2100,
                            chord_sequence=1, armed=True, held=True)
        self.assertEqual(observed, [(0, 0, 72, 144)])
        raw = buffer.raw
        self.assertEqual(raw[:64], bytes([0xA5]) * 64)
        self.assertEqual(struct.unpack_from('<q', raw, 64)[0], 1)
        self.assertEqual(struct.unpack_from('<Q', raw, 64+48)[0], CONFIG['player'])
        self.assertEqual(struct.unpack_from('<3Q', raw, 64+72), tuple(CONFIG['banks']))
        self.assertEqual(struct.unpack_from('<IiII', raw, 64+112), (0xCF0, 4100, 1, 1))
        self.assertEqual(struct.unpack_from('<q', raw, 64+152)[0], 1)
        (ROOT/'work/native-tests/publisher-command.bin').write_bytes(raw[64:])

    def test_release_cannot_revive_old_edge(self):
        intent = dispatch.DispatchIntent(1000)
        intent.process(logical(edge=True), 1000)
        self.assertTrue(intent.fields(1001)['armed'])
        intent.process(logical(lb=False), 1010)
        intent.process(logical(lb=True), 1020)
        self.assertFalse(intent.fields(1021)['armed'])
        self.assertEqual(intent.fields(1021)['expires'], 0)
        intent.process(logical(edge=True), 1030)
        self.assertTrue(intent.fields(1031)['armed'])
        self.assertEqual(intent.chord_sequence, 2)

    def test_hysteresis_and_disconnect_cancel(self):
        intent = dispatch.DispatchIntent(1000)
        intent.process(logical(edge=True, lt=.7), 1000)
        intent.process(logical(lt=.5), 1010)
        self.assertTrue(intent.fields(1011)['armed'])
        intent.process(logical(lt=.4), 1020)
        self.assertFalse(intent.fields(1021)['armed'])
        intent.process(logical(edge=True), 1100)
        intent.process(dict(kind='device_unavailable'), 1110)
        self.assertFalse(intent.fields(1111)['armed'])
        intent.process(dict(kind='device_match', accepted=True), 1120)
        intent.process(logical(), 1130)
        self.assertFalse(intent.fields(1131)['armed'])

    def test_expiry_and_completed_shot_cannot_rearm(self):
        intent = dispatch.DispatchIntent(1000)
        intent.process(logical(edge=True), 1000)
        self.assertFalse(intent.fields(2200)['armed'])
        intent.dispatched()
        intent.process(logical(edge=True), 2300)
        self.assertFalse(intent.fields(2301)['armed'])

    def test_current_profile_prepares_CF0_and_rejects_missing_resource(self):
        profile = json.loads((Path(__file__).resolve().parent/'fixtures/session-profile.json').read_text())
        game = type('Game', (), {'identity': profile['session']})()
        with patch.object(dispatch, 'validate') as validate:
            config = dispatch.prepare(game, profile, 0xCF0)
        self.assertEqual(config['motion'], 4100)
        self.assertEqual(config['player'], int(profile['player']['actor'], 0))
        self.assertEqual(config['banks'], [int(x, 0) for x in profile['player']['action_banks']])
        self.assertEqual(validate.call_count, 1)
        profile['player']['target_actions'][0]['resources']['motion']['present_slots'] = []
        with self.assertRaisesRegex(ValueError, 'motion resource'):
            dispatch.prepare(game, profile, 0xCF0)

    def exercise_main(self, *, close_errors=False, dispatch_once=False):
        calls, instances = [], []
        class Game:
            def __init__(self, pid): pass
            def __enter__(self): return self
            def __exit__(self, *args): return False
        class Command:
            def __init__(self, pid, prefix='NiohDispatchCommand_v1'):
                self.clock = self.controls = 0
                self.published = []
                instances.append(self)
            def control(self):
                self.controls += 1
                return dict(enabled=1, frequency=1000, generation=7,
                            dispatch_count=int(dispatch_once and self.controls > 1))
            def qpc(self):
                self.clock += 50
                return self.clock
            def publish(self, config, **fields): self.published.append(fields)
            def close(self):
                if close_errors: raise RuntimeError('command close failed')
        class Trace:
            def __init__(self, *args): pass
            def header(self):
                if close_errors: raise RuntimeError('trace header failed')
                return dict(enabled=1, frequency=1000, written=0)
            def close(self):
                if close_errors: raise RuntimeError('trace close failed')
        def run(command, outdir, name):
            calls.append(name)
            return json.dumps(dict(status='export_returned', mutation_started=True, result=0))
        with tempfile.TemporaryDirectory(dir=ROOT/'work/native-tests') as temp:
            folder = Path(temp)
            profile, calibration = folder/'profile.json', folder/'calibration.json'
            profile.write_text(json.dumps(dict(session=dict(pid=123, creation_filetime='456'))))
            calibration.write_text(json.dumps(dict(device=dict(backend='winmm'))))
            argv = ['run_dispatch.py', '--profile', str(profile), '--calibration', str(calibration),
                    '--seconds', '.4', '--outdir', str(folder/'result')]
            reader = type('Reader', (), {'poll': lambda self: []})()
            with patch.object(sys, 'argv', argv), patch.object(dispatch, 'LiveGame', Game), \
                 patch.object(dispatch, 'CommandMap', Command), patch.object(dispatch, 'Trace', Trace), \
                 patch.object(dispatch, 'prepare', return_value=CONFIG.copy()), \
                 patch.object(dispatch, 'validate'), patch.object(dispatch, 'run', side_effect=run), \
                 patch.object(dispatch, 'CalibratedChord'), patch.object(dispatch, 'WinMMBackend'), \
                 patch.object(dispatch, 'ControllerReader', return_value=reader), \
                 patch.object(dispatch.time, 'sleep'), contextlib.redirect_stdout(io.StringIO()):
                if close_errors:
                    with self.assertRaises(SystemExit): dispatch.main()
                else:
                    dispatch.main()
            status = json.loads((folder/'result/status.json').read_text())
        return calls, status, instances[0]

    def test_cleanup_exceptions_do_not_skip_stop(self):
        calls, status, command = self.exercise_main(close_errors=True)
        self.assertEqual(calls, ['start', 'stop'])
        self.assertTrue(status['stop_attempted'] and status['stop_completed'])
        self.assertFalse(command.published[-1]['armed'])

    def test_late_dispatch_gets_full_three_second_recovery(self):
        calls, status, command = self.exercise_main(dispatch_once=True)
        self.assertEqual(calls, ['start', 'stop'])
        self.assertEqual(status['dispatch_count'], 1)
        self.assertGreaterEqual(command.clock, 3200)  # original listen deadline was 450
        self.assertTrue(all(not x['armed'] for x in command.published))


if __name__ == '__main__':
    unittest.main()
