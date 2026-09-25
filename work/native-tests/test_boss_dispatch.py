"""Boss publisher checks with Python-owned buffers and mocked orchestration only."""
import contextlib
import copy
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'outputs/okatsu-prototype'))
import run_dispatch as dispatch

FIXTURES = Path(__file__).resolve().parent / 'fixtures'
PROFILE = json.loads((FIXTURES / 'session-profile.json').read_text())
BOSS = json.loads((FIXTURES / 'boss-session.json').read_text())


class OwnedGame:
    def __init__(self, pid):
        self.identity = PROFILE['session'].copy()
        self.memory = {}
        for name, size in [('source_actor', 0x100), ('player', 0x500),
                           ('source_owner', 0x80), ('player_owner', 0x250),
                           ('source_motion', 0xF8), ('player_motion', 0xF8),
                           ('source_timing', 0x80), ('player_timing', 0x80)]:
            self.put(BOSS[name], bytes(size))
        self.put(0x900000, bytes(0x60))
        self.qword(BOSS['source_actor'] + 0x78, BOSS['source_bank'])
        for who in ('source', 'player'):
            self.qword(BOSS[who + '_owner'] + 0x38, BOSS[who + '_motion'])
            self.qword(BOSS[who + '_owner'] + 0x68, BOSS[who + '_timing'])
        self.qword(BOSS['source_motion'] + 8, BOSS['source_motion_bank'])
        self.qword(BOSS['source_timing'] + 0x10, BOSS['source_timing_wrapper'])
        self.qword(BOSS['player_timing'] + 0x40, 0x900000)
        self.qword(0x900020, BOSS['source_timing_record'])
        self.qword(0x900058, 1220)
        self.qword(BOSS['player_motion'] + 0x88, BOSS['source_clip'])
        self.slots(BOSS['originals'])

    def put(self, address, data):
        self.memory.update({address + i: byte for i, byte in enumerate(data)})
    def qword(self, address, value): self.put(address, struct.pack('<Q', value))
    def bytes(self, address, size): return bytes(self.memory[address + i] for i in range(size))
    def begin_sample(self): pass
    def snapshot(self, address):
        owner = BOSS['source_owner'] if address == BOSS['source_actor'] else BOSS['player_owner']
        return self.bytes(address, 0x100), dict(owner_like=hex(owner))
    def slots(self, values):
        addresses = [BOSS['player_motion'] + 8, BOSS['player_motion'] + 0x28,
                     BOSS['player_timing'] + 0x10, BOSS['player_timing'] + 0x28]
        for address, value in zip(addresses, values): self.qword(address, value)
    def __enter__(self): return self
    def __exit__(self, *args): return False


class BossTests(unittest.TestCase):
    def test_source_descriptor_player_identity_and_profile_binding(self):
        with patch.object(dispatch, 'validate'):
            config = dispatch.prepare(OwnedGame(0), PROFILE, 0xC64, boss=True)
        self.assertEqual((config['player'], config['owner']), (BOSS['player'], BOSS['player_owner']))
        self.assertEqual((config['descriptor'], config['payload'], config['motion']),
                         (BOSS['source_descriptor'], BOSS['source_payload'], 1220))
        dispatch.validate_boss_profile(config, PROFILE, BOSS)
        wrong = copy.deepcopy(BOSS)
        wrong['source_clip'] += 8
        with self.assertRaisesRegex(ValueError, 'source clip'):
            dispatch.validate_boss_profile(config, PROFILE, wrong)
        wrong = copy.deepcopy(BOSS)
        wrong['player_owner'] += 8
        with self.assertRaisesRegex(ValueError, 'identities'):
            dispatch.validate_boss_profile(config, PROFILE, wrong)

    def test_four_slots_and_consumed_resources_distinguish_blend_retention(self):
        game = OwnedGame(0)
        state = dispatch.boss_snapshot(game, BOSS, require_originals=True)
        self.assertTrue(state['all_slots_original'])
        self.assertFalse(state['source_clip_current'])
        self.assertTrue(state['source_clip_retained'])
        self.assertTrue(state['source_timing_current'])
        borrowed = [BOSS['source_motion_bank']] * 2 + [BOSS['source_timing_wrapper']] * 2
        game.slots(borrowed)
        self.assertFalse(dispatch.boss_snapshot(game, BOSS)['all_slots_original'])
        with self.assertRaisesRegex(ValueError, 'all been restored'):
            dispatch.boss_snapshot(game, BOSS, require_originals=True)
        game.slots([1, *BOSS['originals'][1:]])
        with self.assertRaisesRegex(ValueError, 'Unexpected player resource'):
            dispatch.boss_snapshot(game, BOSS)

    def test_post_stop_uses_new_read_only_identity_and_logs_retained_clip(self):
        with patch.object(dispatch, 'LiveGame', OwnedGame):
            state = dispatch.verify_boss_after_stop(PROFILE['session'], BOSS)
            self.assertTrue(state['all_slots_original'] and state['source_clip_retained'])
            wrong = dict(PROFILE['session'], creation_filetime='0')
            with self.assertRaisesRegex(ValueError, 'different game process'):
                dispatch.verify_boss_after_stop(wrong, BOSS)

    def test_boss_recovery_stop_busy_retry_and_post_stop_report(self):
        calls, instances, prefixes = [], [], []
        class Command:
            def __init__(self, pid, prefix):
                prefixes.append(prefix)
                self.clock = self.controls = 0
                self.published = []
                instances.append(self)
            def control(self):
                self.controls += 1
                return dict(enabled=1, frequency=1000, generation=7, dispatch_count=int(self.controls > 1))
            def qpc(self): self.clock += 50; return self.clock
            def publish(self, config, **fields): self.published.append(fields)
            def close(self): pass
        class Trace:
            def __init__(self, pid, prefix): prefixes.append(prefix)
            def header(self): return dict(enabled=1, frequency=1000, written=0)
            def close(self): pass
        def run(command, outdir, name):
            calls.append(name)
            if name == 'stop':
                failure = subprocess.CompletedProcess([], 2,
                    json.dumps(dict(status='export_returned', mutation_started=True, result=170)), '')
                raise dispatch.CommandFailure(name, failure)
            return json.dumps(dict(status='export_returned', mutation_started=True, result=0))
        reader = type('Reader', (), {'poll': lambda self: []})()
        resource = dispatch.boss_snapshot(OwnedGame(0), BOSS)
        with tempfile.TemporaryDirectory(dir=ROOT / 'work/native-tests') as temp:
            folder = Path(temp)
            calibration = folder / 'calibration.json'
            calibration.write_text(json.dumps(dict(device=dict(backend='winmm'))))
            argv = ['run_dispatch.py', '--boss', '--profile', str(FIXTURES / 'session-profile.json'),
                    '--calibration', str(calibration), '--seconds', '.4', '--outdir', str(folder / 'result')]
            with patch.object(sys, 'argv', argv), patch.object(dispatch, 'HERE', FIXTURES), \
                 patch.object(dispatch, 'LiveGame', OwnedGame), \
                 patch.object(dispatch, 'CommandMap', Command), patch.object(dispatch, 'Trace', Trace), \
                 patch.object(dispatch, 'validate'), patch.object(dispatch, 'run', side_effect=run), \
                 patch.object(dispatch, 'CalibratedChord'), patch.object(dispatch, 'WinMMBackend'), \
                 patch.object(dispatch, 'ControllerReader', return_value=reader), \
                 patch.object(dispatch.time, 'sleep'), contextlib.redirect_stdout(io.StringIO()):
                dispatch.main()
            status = json.loads((folder / 'result/status.json').read_text())
        self.assertEqual(calls, ['start', 'stop', 'stop-retry1'])
        self.assertEqual(prefixes, ['NiohBossCommand_v1', 'NiohBossTrace_v1'])
        self.assertTrue(status['stop_completed'] and status['post_stop_slots_restored'])
        self.assertTrue(status['post_stop_resources']['source_clip_retained'])
        self.assertEqual(status['stop_busy_retries'], 1)
        self.assertEqual(status['recovery_seconds'], 5)
        self.assertEqual(status['errors'], [])
        self.assertGreaterEqual(instances[0].clock, 5300)
        self.assertFalse(instances[0].published[-1]['armed'])


if __name__ == '__main__':
    unittest.main()
