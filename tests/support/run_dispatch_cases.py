# Offline regression cases for controller/session ownership and cooperative dispatcher shutdown.
# Fixtures isolate game/process effects; these checks do not establish gameplay acceptance.
# Loaded by the existing Engine test entrypoints through Test-Offline.ps1; see CODE_GUIDE.md.
import contextlib
import ctypes as C
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
MOD_ROOT = ROOT/'mwm'
sys.path.insert(0, str(ROOT / 'runtime'))
import run_dispatch as dispatch
from session_fixture import PROFILE, BOSS

CONFIG = dict(generation=7, player=0x100000, owner=0x200000, vtable=0x300000,
              banks=[0x400000, 0x500000, 0x600000], descriptor=0x700000,
              payload=0x800000, key=0xCF0, motion=4100)


class DispatchTests(unittest.TestCase):
    def test_pack_layout_and_uncommitted_markers_during_body_copy(self):
        # Keep sequence markers uncommitted while command payload bytes are copied.
        # Observe publication markers during the owned command-body copy and unpack its fields.
        # The native consumer must never accept a partially written command.
        buffer = C.create_string_buffer(bytes([0xA5]) * 224, 224)
        command = dispatch.CommandMap.__new__(dispatch.CommandMap)
        command.address, command.sequence = C.addressof(buffer), 0
        real_copy = C.memmove
        observed = []
        def copying(address, body, length):
            # Observe the seqlock markers while command payload copying is in progress.
            # Read begin at mapping+64 and end at mapping+216 before the real owned-memory copy.
            # Readers must never accept the command body while either publication marker is uncommitted.
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
        from engine_config import DEFAULT_PRESET, binding_for_preset
        from game_controller import GAME_DEVICE, game_binding
        ds4=json.loads((MOD_ROOT/'data/controller-calibration.json').read_text())
        for calibration,triggers in ((ds4,(8,4,64)),(dict(device=GAME_DEVICE,lb_mask=0x100),(0x8000,0x2000,0x400))):
            for raw_trigger,logical in zip(triggers,(0x8000,0x2000,0x400)):
                for stance,mask in (('low',1),('high',4),('any',7)):
                    preset=dict(DEFAULT_PRESET,tap_move='okatsu.charged_rush',hold_move=None,
                        modifier_mask=calibration['lb_mask'],trigger_mask=raw_trigger,chord_stance=stance)
                    _,binding=game_binding(calibration,binding_for_preset(calibration,preset))
                    policy=((0x100|logical)<<16)|(mask<<32)
                    self.assertEqual(binding['chord_policy'],policy)
                    command.publish(dict(CONFIG,chord_policy=binding['chord_policy']),heartbeat=1000,edge=900,
                        expires=2100,chord_sequence=1,armed=True,held=False,latched=1,context_epoch=23)
                    self.assertEqual(struct.unpack_from('<3Q',buffer.raw,64+128),(policy|1,0,23))
                    preset.update(tap_move=None,hold_move=None)
                    _,disabled=game_binding(calibration,binding_for_preset(calibration,preset))
                    self.assertEqual(disabled['chord_policy'],0)
            preset=dict(DEFAULT_PRESET,modifier_mask=calibration['lb_mask'],
                trigger_mask=32 if calibration['device']['backend']=='winmm' else 0x200)
            with self.assertRaisesRegex(ValueError,'reserved for Ki Pulse and Frost Moon'):
                game_binding(calibration,binding_for_preset(calibration,preset))
            preset.update(tap_move=None,hold_move=None)
            self.assertEqual(game_binding(calibration,binding_for_preset(calibration,preset))[1]['chord_policy'],0)


    def test_current_profile_prepares_source_and_rejects_missing_resource(self):
        # Resolve the current source resources and reject absent dependencies.
        # Build the probe profile from its resolved action and required motion resource.
        # A valid action key alone cannot make an import executable without matching assets.
        profile = json.loads(json.dumps(PROFILE))
        game = type('Game', (), {'identity': profile['session']})()
        with patch.object(dispatch, 'validate') as validate:
            config = dispatch.prepare(game, profile)
        self.assertEqual(config['motion'], 1220)
        self.assertEqual(config['player'], int(profile['player']['actor'], 0))
        self.assertEqual(config['banks'], [int(x, 0) for x in profile['player']['action_banks']])
        self.assertEqual(validate.call_count, 1)
        profile['source']['resources']['motion']['present_slots'] = []
        with self.assertRaisesRegex(ValueError, 'motion resource'):
            dispatch.prepare(game, profile)

    def exercise_main(self, *, close_errors=False, dispatch_once=False, start_failure=None,
                      calibration_change=None, prepared_selection=None):
        # Run dispatcher startup and cleanup against fake mappings and exports.
        # Optionally inject disposal failures or a dispatch observed late during shutdown.
        # Native Stop and recovery waiting must survive errors from other cleanup steps.
        calls, instances = [], []
        class Game:
            def __init__(self, pid):
                # Accept the dispatcher's requested process id without attaching.
                # Allocate no handle because this fixture only satisfies lifecycle structure.
                # Cleanup tests must not depend on a running game.
                pass
            def __enter__(self):
                # Enter the fake dispatcher process context.
                # Return the fixture without acquiring an external resource.
                # The real startup and shutdown scope remains exercised offline.
                return self
            def __exit__(self, *args):
                # Leave the fake dispatcher context without suppressing failures.
                # Return false because there is no process handle to dispose.
                # Unexpected cleanup exceptions must remain observable to the test runner.
                return False
        class Command:
            def __init__(self, pid, tag):
                # Create deterministic command control and publication history.
                # Register this fixture so the test can inspect final disarming fields.
                # Shutdown assertions must follow the actual supervisor publications.
                self.clock = self.controls = 0
                self.published = []
                instances.append(self)
            def control(self):
                # Advance control observations and optionally reveal a late dispatch.
                # Report the count change after the initial poll while keeping the runtime enabled.
                # Recovery grace must begin when the last accepted dispatch is observed.
                self.controls += 1
                return dict(enabled=1, frequency=1000, generation=7,
                            dispatch_count=int(dispatch_once and self.controls > 1), context_flags=15, context_epoch=0)
            def qpc(self):
                # Advance the mocked command counter by 50 ticks.
                # Use the same 1000-Hz frequency exposed by control and trace.
                # Recovery deadlines can be measured without a real-time delay.
                self.clock += 50
                return self.clock
            def publish(self, config, **fields):
                # Record all command fields published during dispatcher execution.
                # Keep immutable call arguments in the fixture's history.
                # The final command must remain disarmed even when cleanup later fails.
                self.published.append(fields)
            def close(self):
                # Inject command disposal failure only when the scenario requests it.
                # Otherwise leave the owned fixture untouched.
                # A close error must not prevent the independent native Stop attempt.
                if close_errors or start_failure is not None: raise RuntimeError('command close failed')
        class Trace:
            def __init__(self, *args, **kwargs):
                # Accept trace attachment arguments without opening a mapping.
                # Keep the fixture empty because only header and cleanup behavior are needed.
                # The shutdown test must not read a live game's trace.
                pass
            def header(self):
                # Return an empty enabled trace or the selected header failure.
                # Keep its QPC frequency aligned with the command fixture.
                # Stop cleanup must still run when trace inspection itself raises.
                if close_errors or start_failure is not None: raise RuntimeError('trace header failed')
                return dict(enabled=1, frequency=1000, written=0)
            def close(self):
                # Inject the scenario's trace disposal error.
                # Perform no work for the successful cleanup branch.
                # Independent cleanup operations must each be attempted after an earlier failure.
                if close_errors or start_failure is not None: raise RuntimeError('trace close failed')
        def run(command, outdir, name):
            # Acknowledge each native export stage and log its order.
            # Return structured completed-export evidence without starting an injector.
            # The test can prove Stop was attempted despite mapping cleanup errors.
            calls.append(name)
            if name == 'start' and start_failure is not None:
                raise start_failure
            return json.dumps(dict(status='export_returned', mutation_started=True, result=0))
        with tempfile.TemporaryDirectory(dir=ROOT/'tests/native') as temp:
            folder = Path(temp)
            profile, calibration = folder/'profile.json', folder/'calibration.json'
            profile.write_text(json.dumps(PROFILE))
            (folder/'boss-session.json').write_text(json.dumps(dict(BOSS,
                controller_selection=0 if prepared_selection is None else prepared_selection)))
            calibration.write_text((MOD_ROOT/'data/controller-calibration.json').read_text())
            (folder/'controller-binding.json').write_text((MOD_ROOT/'data/preset.json').read_text())
            argv = ['run_dispatch.py', '--profile', str(profile), '--calibration', str(calibration),
                    '--seconds', '.4', '--outdir', str(folder/'result')]
            changed=False
            def poll(self):
                # Supply the next test-controlled controller sample to the dispatcher.
                # Keep the observation stream deterministic while the production dispatch loop runs.
                # This fixture feeds data directly and does not read a physical controller or send game input.
                nonlocal changed
                if calibration_change and not changed:
                    value=json.loads(calibration.read_text())
                    if calibration_change=='slot': value['controller_slot']=1
                    if calibration_change=='map': value['button_map']={'4':0x2000,'16':0x100}
                    stamp=calibration.stat().st_mtime_ns
                    calibration.write_text(json.dumps(value))
                    os.utime(calibration,ns=(stamp+1_000_000,stamp+1_000_000))
                    changed=True
                return []
            reader = type('Reader', (), {'poll': poll})()
            with patch.object(sys, 'argv', argv), patch.object(dispatch, 'HERE', folder), patch.object(dispatch, 'LiveGame', Game), \
                 patch.object(dispatch, 'CommandMap', Command), patch.object(dispatch, 'Trace', Trace), \
                 patch.object(dispatch, 'prepare', return_value=CONFIG.copy()), \
                 patch.object(dispatch, 'validate'), patch.object(dispatch, 'run', side_effect=run), \
                 patch.object(dispatch, 'validate_boss_profile'), \
                 patch.object(dispatch, 'boss_snapshot', return_value={'all_slots_original':True}), \
                 patch.object(dispatch, 'verify_boss_after_stop', return_value={'all_slots_original':True}), \
                 patch.object(dispatch, 'ControllerReader', return_value=reader), \
                 patch.object(dispatch.time, 'sleep'), contextlib.redirect_stdout(io.StringIO()):
                if prepared_selection is not None:
                    with self.assertRaisesRegex(ValueError,'Controller selection changed'):
                        dispatch.main()
                    return calls,{},None
                if close_errors or start_failure is not None or calibration_change in ('slot','map'):
                    with self.assertRaises(SystemExit): dispatch.main()
                else:
                    dispatch.main()
            status = json.loads((folder/'result/status.json').read_text())
        return calls, status, instances[0] if instances else None

    def test_calibration_edits_require_reacquisition_but_identical_rewrite_does_not(self):
        # Check whether controller-calibration changes invalidate an active dispatch session.
        # Compare a meaningful configuration change with rewriting identical content.
        # Only changed binding identity should force reacquisition; filesystem timestamps alone are insufficient.
        for change in ('slot','map','touch'):
            calls,status,command=self.exercise_main(calibration_change=change)
            self.assertEqual(calls,['start','stop'])
            self.assertFalse(command.published[-1]['armed'])
            self.assertEqual(any('Controller calibration changed' in error for error in status['errors']),change!='touch')

    def test_prepared_controller_selection_must_match_before_start(self):
        # Reject dispatch when the prepared session used a different controller selection.
        # Compare the current calibration with the selection embedded in session data.
        # This prevents a valid-looking preset from starting against the wrong controller's native observations.
        calls,_,_=self.exercise_main(prepared_selection=2)
        self.assertEqual(calls,[])

    def test_cleanup_exceptions_do_not_skip_stop(self):
        # Attempt native Stop even when trace or command cleanup raises.
        # Raise errors from command close, trace header and trace close during cleanup.
        # Each cleanup step must still reach the independent native Stop operation.
        calls, status, command = self.exercise_main(close_errors=True)
        self.assertEqual(calls, ['start', 'stop'])
        self.assertTrue(status['stop_attempted'] and status['stop_completed'])
        self.assertFalse(command.published[-1]['armed'])

    def test_accepted_dispatch_is_disarmed_before_native_stop(self):
        # Preserve native recovery when a dispatch is accepted near the capture deadline.
        # Advance the native dispatch counter while the bounded publisher is running.
        # Final disarming precedes Stop, which owns the actual recovery lifetime.
        calls, status, command = self.exercise_main(dispatch_once=True)
        self.assertEqual(calls, ['start', 'stop'])
        self.assertEqual(status['dispatch_count'], 1)
        self.assertTrue(all(not x['armed'] for x in command.published))

    def test_start_failures_stop_only_when_native_mutation_is_possible(self):
        # Keep loader preflight failures separate from uncertain remote execution.
        # Reuse the production publisher cleanup path for structured and unknown failures.
        # A proven untouched process skips Stop; possible mutation always attempts it.
        for mutation in (False, True, None):
            with self.subTest(mutation=mutation):
                failure = RuntimeError('No loader diagnostic') if mutation is None else dispatch.CommandFailure(
                    'start', subprocess.CompletedProcess([],1,'',json.dumps({'status':'error','mutation_started':mutation})))
                calls,status,_ = self.exercise_main(start_failure=failure)
                self.assertEqual(calls,['start'] if mutation is False else ['start','stop'])
                self.assertEqual(status['stop_attempted'],mutation is not False)
