import copy
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'runtime'), str(ROOT/'catalogue')]
import engine_config as config
import process_support as process
import trainer
from gestures import ControllerGesture


class PresetTests(unittest.TestCase):
    def test_malformed_move_types_are_validation_errors_not_callback_crashes(self):
        # Reject malformed move field types as validation errors before GUI callbacks fail.
        # Pass invalid move data shapes into preset validation.
        # User configuration errors must be reported explicitly before GUI callbacks dereference fields.
        for field in ('tap_move', 'hold_move'):
            for value in ([], {}, 1, True):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    config.validate_preset(dict(config.DEFAULT_PRESET, **{field: value}))

    def test_missing_required_fields_and_boolean_version_are_validation_errors(self):
        # Reject missing configuration fields and boolean version values explicitly.
        # Remove required preset fields and supply a boolean schema version.
        # Loose Python integer compatibility must not admit malformed versioned configuration.
        for value in ({'schema_version': 1}, dict(config.DEFAULT_PRESET, schema_version=2),
                      dict(config.DEFAULT_PRESET, schema_version=True)):
            with self.assertRaises(ValueError):
                config.validate_preset(value)

    def test_nonfinite_hold_and_impossible_masks_are_rejected(self):
        # Reject nonfinite hold durations and impossible controller masks.
        # Set nonfinite hold durations and invalid or overlapping button masks.
        # Invalid bindings must fail before they can enter gesture recognition.
        for value in (float('nan'), float('inf'), -.1, True):
            with self.assertRaises(ValueError):
                config.validate_preset(dict(config.DEFAULT_PRESET, hold_seconds=value))
        for value in (0, 3, 1 << 32, True):
            with self.assertRaises(ValueError):
                config.validate_preset(dict(config.DEFAULT_PRESET, trigger_mask=value))

    def test_frost_slots_and_window_reject_unsupported_or_conflicting_bindings(self):
        # Enable low Flying Swallow, mid Izuna and high overhead Frost Moon in the baseline.
        # Reject malformed windows, unsupported skills and one import assigned to different stances.
        # Shared hold and Frost bindings may reuse a skill only within the same native stance.
        preset=copy.deepcopy(config.DEFAULT_PRESET)
        self.assertEqual(config.validate_preset(preset)['frost_moon'],
                         dict(low='jin_hayabusa.action_0c71',mid='jin_hayabusa.action_0c81',high=None))
        self.assertEqual(preset['frost_startup_speed'],8)
        for value in (0,9,True,8.0,'8'):
            with self.subTest(speed=value), self.assertRaises(ValueError):
                config.validate_preset(dict(preset,frost_startup_speed=value))
        self.assertEqual(config.validate_preset(dict(preset,frost_startup_speed=1))['frost_startup_speed'],1)
        for value in (float('nan'),float('inf'),.099,1.501,True,'0.75'):
            with self.subTest(window=value), self.assertRaises(ValueError):
                config.validate_preset(dict(preset,frost_window_seconds=value))
        for value in (None,{},dict(low=None,mid=None),dict(low=None,mid=None,high='jin_hayabusa.action_0c79'),
                      dict(low='jin_hayabusa.action_0cac',mid=None,high='jin_hayabusa.action_0cac'),
                      dict(low='jin_hayabusa.izuna_drop',mid=None,high='jin_hayabusa.action_0cac'),
                      dict(low='jin_hayabusa.action_0c81',mid=None,high='jin_hayabusa.action_0c81')):
            with self.subTest(slots=value), self.assertRaises(ValueError):
                config.validate_preset(dict(preset,frost_moon=value))
        preset['stance_holds']['mid']='jin_hayabusa.action_0c71'
        with self.assertRaisesRegex(ValueError,'same stance'):
            config.validate_preset(preset)
        preset['stance_holds']['mid']=None
        preset['stance_holds']['high']='jin_hayabusa.izuna_drop'
        self.assertEqual(config.validate_preset(preset),preset)

    def test_saved_mapping_reconnect_never_fires_a_held_gesture(self):
        # Prevent saved held mappings from firing immediately after reconnect.
        # Reload the saved calibration and reconnect with the bound controls held.
        # Persisted mappings remove recalibration work but do not authorize synthetic presses.
        calibration = json.loads((ROOT/'runtime/controller-calibration.json').read_text())
        binding = config.binding_for_preset(calibration, config.DEFAULT_PRESET)
        gate = ControllerGesture(calibration, binding, 1000)
        device = calibration['device']
        common = {k: device[k] for k in ('backend', 'slot')}
        gate.process(dict(kind='input_device', **device), 100)
        gate.process(dict(kind='input', buttons=20, edge_basis='unknown', **common), 110)
        self.assertFalse(gate.fields(1000)['armed'])
        gate.process(dict(kind='input_unavailable', **common), 1100)
        gate.process(dict(kind='input_device', **device), 1200)
        gate.process(dict(kind='input', buttons=20, edge_basis='unknown', **common), 1210)
        self.assertFalse(gate.fields(2000)['armed'])
        gate.process(dict(kind='input', buttons=0, **common), 2100)
        gate.process(dict(kind='input', buttons=20, **common), 2200)
        gate.process(dict(kind='input', buttons=16, **common), 2250)
        self.assertTrue(gate.fields(2251)['armed'])
        self.assertEqual(gate.fields(2251)['variant'], 0)


class RuntimeRegistryTests(unittest.TestCase):
    def test_registry_requires_current_process_birth_not_just_pid(self):
        # Bind registry ownership to process birth rather than a recycled PID.
        # Reuse a runtime registry PID with a different creation identity.
        # Cross-installation discovery must not attach to an unrelated replacement process.
        with tempfile.TemporaryDirectory() as td:
            registry = Path(td)/'active.json'
            registry.write_text(json.dumps({'runtime_path': td, 'publisher_pid': 42, 'publisher_start_filetime': 'old'}))
            with patch.object(process, 'runtime_registry_path', return_value=registry), \
                 patch.object(process, 'process_identity', return_value={'publisher_pid': 42, 'publisher_start_filetime': 'new'}):
                self.assertIsNone(process.active_runtime())

    def test_register_discover_cleanup_and_no_deleting_another_owner(self):
        # Remove only this process's registry record during cleanup.
        # Register a runtime, discover it and replace its owner before cleanup.
        # Only the process that still owns a registry record may delete it.
        with tempfile.TemporaryDirectory() as td:
            registry = Path(td)/'registry'/'active.json'
            identity = {'publisher_pid': 42, 'publisher_start_filetime': 'birth'}
            with patch.object(process, 'runtime_registry_path', return_value=registry), \
                 patch.object(process, 'process_identity', return_value=identity):
                record = process.register_runtime(td, Path(td)/'moves.xlsx')
                self.assertEqual(process.active_runtime(), record)
                replacement = dict(record, publisher_pid=43)
                registry.write_text(json.dumps(replacement))
                process.unregister_runtime(record)
                self.assertTrue(registry.exists())
                registry.write_text(json.dumps(record))
                process.unregister_runtime(record)
                self.assertFalse(registry.exists())

    def test_disable_and_enable_target_active_runtime_across_installs(self):
        # Target the active runtime when enabling or disabling across installations.
        # Point the registry at an active runtime outside the current checkout.
        # Trainer controls must operate on the actual running engine rather than local stale files.
        with tempfile.TemporaryDirectory() as td:
            other, local = Path(td)/'other-install', Path(td)/'this-install'
            other.mkdir(); local.mkdir()
            with patch.object(trainer, 'RUNTIME', local), \
                 patch.object(trainer, 'active_runtime', return_value={'runtime_path': str(other)}), \
                 patch.object(trainer, 'launch') as launch:
                self.assertIsNone(trainer.launch_engine())
                launch.assert_not_called()
                trainer.disable_engine()
                self.assertTrue((other/'stop.flag').exists())
                self.assertFalse((local/'stop.flag').exists())

    def test_disable_cli_does_not_construct_any_gui(self):
        # Keep command-line disable independent of GUI construction.
        # Invoke the trainer's disable worker through its command-line path.
        # An automated stop request must not create a window or initialize interactive UI state.
        with tempfile.TemporaryDirectory() as td, patch.object(trainer, 'RUNTIME', Path(td)), \
             patch.object(trainer, 'active_runtime', return_value=None), patch.object(trainer, 'Trainer') as ui:
            self.assertEqual(trainer.main(['--disable']), 0)
            ui.assert_not_called()
            self.assertTrue((Path(td)/'stop.flag').exists())

    def test_open_trainer_adopts_other_runtime_before_applying_pending_edit(self):
        # Adopt another active runtime before applying a pending trainer edit.
        # Present an already-running external runtime while the open trainer has a pending edit.
        # The trainer must adopt current ownership before deciding whether the edit can be applied.
        calibration = json.loads((ROOT/'runtime/controller-calibration.json').read_text())
        binding = config.binding_for_preset(calibration, config.DEFAULT_PRESET)
        desired = dict(config.DEFAULT_PRESET, name='Pending user edit', hold_seconds=.35)
        with tempfile.TemporaryDirectory() as td:
            local, other = Path(td)/'local', Path(td)/'other'
            local.mkdir(); other.mkdir()
            for folder in (local, other):
                (folder/'controller-calibration.json').write_text(json.dumps(calibration))
                (folder/'controller-binding.json').write_text(json.dumps(config.DEFAULT_PRESET))
            catalogue = Path(td)/'moves.xlsx'
            registration = {'runtime_path': str(other), 'catalogue_path': str(catalogue),
                            'publisher_pid': 42, 'publisher_start_filetime': 'birth'}
            messages = []
            app = SimpleNamespace(adopt_running=True, runtime_registration=None, catalogue_path=catalogue,
                calibration=calibration, binding=binding, preset=dict(config.DEFAULT_PRESET),
                refresh_table=lambda: (
                    # Skip visual table refresh in the handle-free trainer fixture.
                    # Return without constructing any widget or touching display state.
                    # Runtime adoption ordering can then be checked independently of rendering.
                    None
                ), notice=SimpleNamespace(set=messages.append),
                form=lambda: (
                    # Return the fixture's desired configuration to the trainer callback.
                    # Preserve the exact object selected by the scenario.
                    # Pending edits must be evaluated against the newly adopted runtime owner.
                    desired
                ), load_fields=lambda value: (
                    # Skip writing adopted binding values into absent form widgets.
                    # Accept the selected configuration while leaving the fixture's form intact.
                    # Pending-edit persistence can then be checked without constructing a GUI.
                    None
                ), error=lambda error: (
                    # Turn trainer apply errors into immediate test failures.
                    # Pass the reported error text to unittest's failure path.
                    # A reported configuration error must not look like successful runtime adoption.
                    self.fail(str(error))
                ))
            app.set_runtime = trainer.Trainer.set_runtime.__get__(app)
            app.adopt_active_runtime = trainer.Trainer.adopt_active_runtime.__get__(app)
            with patch.object(trainer, 'RUNTIME', local), patch.dict(os.environ), \
                 patch.object(trainer, 'active_runtime', return_value=registration), \
                 patch.object(trainer, 'load_catalogue', return_value={'moves': []}), \
                 patch('controller_reader.WinMMBackend'), patch('controller_reader.ControllerReader'):
                self.assertTrue(trainer.Trainer.apply(app))
                self.assertEqual(trainer.RUNTIME, other)
                self.assertEqual(app.runtime_registration, registration)
            saved = json.loads((other/'controller-binding.json').read_text())
            self.assertEqual(saved, desired)
            self.assertEqual(json.loads((local/'controller-binding.json').read_text()), config.DEFAULT_PRESET)


class TrainerWorkerTests(unittest.TestCase):

    def test_workbook_failure_does_not_hide_successful_catalogue_save(self):
        # Report catalogue save success separately from a blocked workbook update.
        # Save a catalogue change and then simulate Excel locking the workbook.
        # The result must distinguish persisted configuration from incomplete spreadsheet synchronization.
        messages = []
        app = SimpleNamespace(catalogue_path='fixture.json', notice=SimpleNamespace(set=messages.append))
        def locked(path):
            # Simulate an Excel lock only at the workbook synchronization step.
            # Raise PermissionError after the catalogue update has already succeeded.
            # The trainer must report partial completion without undoing saved move configuration.
            raise PermissionError('Workbook is open in Excel')
        fake_sync = SimpleNamespace(sync_workbook=locked)
        with patch.dict(sys.modules, {'spreadsheet_sync': fake_sync}):
            trainer.Trainer.sync_catalogue_workbook(app, 'Catalogue name saved.')
        self.assertIn('Catalogue name saved.', messages[0])
        self.assertIn('Excel', messages[0])
