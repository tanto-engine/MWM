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

from session_fixture import BOSS, PROFILE, FIXTURES


class OwnedGame:
    def __init__(self, pid):
        # Build player components and owned resources from the prepared session fixture.
        # Populate the native vtables, ownership links and original resource slots.
        # The dispatch audit must work without any source boss actor existing.
        self.identity = PROFILE['session'].copy()
        self.memory = {}
        for name, size in [('player', 0x500), ('player_owner', 0x250),
                           ('source_action_resource', 0x478), ('source_timing_resource', 0x478),
                           ('source_motion_bank', 0x100), ('player_motion', 0xF8), ('player_timing', 0x80)]:
            self.put(BOSS[name], bytes(size))
        self.put(0x900000, bytes(0x60))
        base = int(self.identity['module_base'], 0)
        self.qword(BOSS['source_action_resource'], base + 0x13C7970)
        self.qword(BOSS['source_action_resource'] + 0x468, BOSS['source_bank'])
        self.qword(BOSS['source_timing_resource'], base + 0x12C5408)
        self.qword(BOSS['source_timing_resource'] + 0x468, BOSS['source_timing_wrapper'])
        self.qword(BOSS['source_motion_bank'], base + 0x13C8FA0)
        self.qword(BOSS['player_owner'] + 0x38, BOSS['player_motion'])
        self.qword(BOSS['player_owner'] + 0x68, BOSS['player_timing'])
        self.qword(BOSS['player_timing'] + 0x40, 0x900000)
        self.qword(0x900020, BOSS['source_timing_record'])
        self.qword(0x900058, 1220)
        self.qword(BOSS['player_motion'] + 0x88, BOSS['source_clip'])
        self.slots(BOSS['originals'])

    def put(self, address, data):
        # Install bytes into the sparse owned-memory fixture.
        # Address each byte explicitly so overlapping pointer writes replace prior values.
        # Tests can mutate one binding without allocating or opening game memory.
        self.memory.update({address + i: byte for i, byte in enumerate(data)})
    def qword(self, address, value):
        # Write one native 64-bit pointer into owned fixture memory.
        # Pack little-endian bytes through the fixture's sparse writer.
        # Pointer mutations must use the same width as the runtime ABI.
        self.put(address, struct.pack('<Q', value))
    def bytes(self, address, size):
        # Read exactly the requested range from the sparse fixture.
        # Require every addressed byte to have been populated by setup.
        # Missing fixture ownership data must surface instead of resembling zeroed memory.
        return bytes(self.memory[address + i] for i in range(size))
    def begin_sample(self):
        # Satisfy the sampler boundary for stable owned fixture memory.
        # Keep this operation empty because the fixture performs no OS region caching.
        # Dispatcher checks can exercise the production interface without process access.
        pass
    def snapshot(self, address):
        # Expose only the fixture's player actor and recorded owner.
        # Reject any attempt to snapshot a source boss before returning player bytes.
        # Owned resource validation must not depend on borrowed boss-object pointers.
        if address != BOSS['player']:
            raise AssertionError('No source actor exists in the owned-resource fixture')
        return self.bytes(address, 0x100), dict(owner_like=hex(BOSS['player_owner']))
    def slots(self, values):
        # Set both current and retained motion/timing slots in one fixture step.
        # Write motion offsets 8/0x28 and timing offsets 0x10/0x28 separately.
        # Recovery must account for resources retained by animation blending.
        addresses = [BOSS['player_motion'] + 8, BOSS['player_motion'] + 0x28,
                     BOSS['player_timing'] + 0x10, BOSS['player_timing'] + 0x28]
        for address, value in zip(addresses, values): self.qword(address, value)
    def __enter__(self):
        # Enter the owned-memory audit through the LiveGame context protocol.
        # Return this fixture without acquiring any process handle.
        # The production audit can be exercised with its normal lifetime structure.
        return self
    def __exit__(self, *args):
        # Leave the owned-memory audit without swallowing assertion failures.
        # Return false because the fixture owns no external handle to close.
        # A bad ownership read must fail the test at its original site.
        return False


class BossTests(unittest.TestCase):
    def test_source_descriptor_player_identity_and_profile_binding(self):
        # Reject mismatched source descriptors, player identities and profile bindings.
        # Validate the configured player and source descriptor using owned resource memory.
        # Boss adaptation must reject stale identity or mismatched profile bindings.
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
        # Distinguish retained blend resources from all four active borrowed slots.
        # Populate current and retained motion/timing slots with source and original banks.
        # Restoration must report resources still consumed by blending instead of claiming clean recovery.
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
        boss=copy.deepcopy(BOSS)
        group=dict(action_resource=0xA10000,timing_resource=0xA20000,bank=0xA30000,
                   motion_bank=0xA40000,timing_wrapper=0xA50000)
        boss['adapters'].append(group)
        base=int(game.identity['module_base'],0)
        for field,vtable in (('action_resource',0x13C7970),('timing_resource',0x12C5408),('motion_bank',0x13C8FA0)):
            game.qword(group[field],base+vtable)
        game.qword(group['action_resource']+0x468,group['bank'])
        game.qword(group['timing_resource']+0x468,group['timing_wrapper'])
        jin=[group['motion_bank']]*2+[group['timing_wrapper']]*2
        game.slots(jin)
        self.assertFalse(dispatch.boss_snapshot(game,boss)['all_slots_original'])
        game.slots([jin[0],BOSS['originals'][1],jin[2],BOSS['originals'][3]])
        dispatch.boss_snapshot(game,boss)
        game.slots([jin[0],borrowed[1],jin[2],jin[3]])
        with self.assertRaisesRegex(ValueError,'mixed group'):dispatch.boss_snapshot(game,boss)
        game.slots(jin);game.qword(group['timing_resource']+0x468,0xBAD000)
        with self.assertRaisesRegex(ValueError,'ownership changed'):dispatch.boss_snapshot(game,boss)

    def test_post_stop_uses_new_read_only_identity_and_logs_retained_clip(self):
        # Inspect recovery using a newly attached read-only identity after Stop.
        # Audit Stop through a newly opened fixture view with retained animation resources.
        # A completed export alone cannot prove the player's resource slots are restored.
        with patch.object(dispatch, 'LiveGame', OwnedGame):
            state = dispatch.verify_boss_after_stop(PROFILE['session'], BOSS)
            self.assertTrue(state['all_slots_original'] and state['source_clip_retained'])
            wrong = dict(PROFILE['session'], creation_filetime='0')
            with self.assertRaisesRegex(ValueError, 'different game process'):
                dispatch.verify_boss_after_stop(wrong, BOSS)

    def test_boss_recovery_stop_busy_retry_and_post_stop_report(self):
        # Wait through busy Stop responses and report the actual recovered resources.
        # Simulate a late dispatch, busy Stop and subsequent read-only restoration audit.
        # Shutdown must retain recovery time and publish the actual post-Stop state.
        calls, instances, prefixes = [], [], []
        class Command:
            def __init__(self, pid, prefix):
                # Capture command mapping identity for the mocked recovery supervisor.
                # Start deterministic control counters and retain every published command.
                # The test can inspect disarming and namespace selection after Stop reports busy.
                prefixes.append(prefix)
                self.clock = self.controls = 0
                self.published = []
                instances.append(self)
            def control(self):
                # Expose an enabled runtime whose dispatch count advances after polling.
                # Increment the count only after the first control observation.
                # The supervisor must allow recovery for a dispatch observed late in shutdown.
                self.controls += 1
                return dict(enabled=1, frequency=1000, generation=7, dispatch_count=int(self.controls > 1))
            def qpc(self):
                # Advance the command clock in deterministic 50-tick steps.
                # Use the mocked 1000-Hz frequency to drive bounded recovery polling.
                # The Stop retry test must complete without waiting on wall-clock gameplay.
                self.clock += 50; return self.clock
            def publish(self, config, **fields):
                # Retain each command publication made during supervisor recovery.
                # Record the supplied fields without contacting a shared mapping.
                # Assertions can verify the final command is disarmed even after busy Stop.
                self.published.append(fields)
            def close(self):
                # Close the command fixture without introducing a second failure.
                # Perform no work because this mapping exists only as Python data.
                # The test isolates busy native Stop from unrelated disposal errors.
                pass
        class Trace:
            def __init__(self, pid, prefix):
                # Record the trace namespace selected by the boss dispatcher.
                # Avoid creating a real mapping for the requested process id.
                # Both trace and command channels must use the configured runtime prefix.
                prefixes.append(prefix)
            def header(self):
                # Return an enabled empty trace at the fixture's QPC frequency.
                # Report zero records while the separate command control advances dispatch count.
                # Shutdown must rely on control state even when no trace record is available.
                return dict(enabled=1, frequency=1000, written=0)
            def close(self):
                # Dispose the empty trace fixture without touching OS handles.
                # Keep the no-op separate from command and native Stop observations.
                # The recovery test must attribute retries to Stop's busy result alone.
                pass
        def run(command, outdir, name):
            # Simulate completed native exports and a busy Stop return.
            # Raise a structured CommandFailure only for the stop stage.
            # The supervisor must retry uncertain restoration without treating it as success.
            calls.append(name)
            if name == 'stop':
                failure = subprocess.CompletedProcess([], 2,
                    json.dumps(dict(status='export_returned', mutation_started=True, result=170)), '')
                raise dispatch.CommandFailure(name, failure)
            return json.dumps(dict(status='export_returned', mutation_started=True, result=0))
        reader = type('Reader', (), {'poll': lambda self: (
            # Keep the mocked controller neutral throughout shutdown recovery.
            # Return no input events from the replacement reader.
            # Busy Stop handling must be driven by native control state, not fresh gestures.
            []
        )})()
        resource = dispatch.boss_snapshot(OwnedGame(0), BOSS)
        with tempfile.TemporaryDirectory(dir=ROOT / 'work/native-tests') as temp:
            folder = Path(temp)
            (folder / 'session-profile.json').write_text(json.dumps(PROFILE))
            (folder / 'boss-session.json').write_text(json.dumps(BOSS))
            calibration = folder / 'calibration.json'
            calibration.write_text(json.dumps(dict(device=dict(backend='winmm'))))
            argv = ['run_dispatch.py', '--boss', '--profile', str(folder / 'session-profile.json'),
                    '--calibration', str(calibration), '--seconds', '.4', '--outdir', str(folder / 'result')]
            with patch.object(sys, 'argv', argv), patch.object(dispatch, 'HERE', folder), \
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
