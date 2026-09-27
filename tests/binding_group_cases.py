"""Product binding composition and editor recovery, through Engine's offline entrypoint."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'app'))
import binding_groups as groups
import web_worker as worker
from game_controller import game_button_mask


class BindingGroupTests(unittest.TestCase):
    def test_terminal_attachment_failure_remains_visible_after_worker_exit(self):
        # A failed resource loader stops its supervisor instead of retrying indefinitely.
        # Keep its failure text visible even though the process is no longer running.
        # Stale enabled status must still collapse to disabled when its owner has exited.
        with tempfile.TemporaryDirectory() as folder:
            runtime = Path(folder)
            with patch.object(worker.Desktop, 'location', return_value=runtime), patch.object(worker, 'process_matches', return_value=False):
                worker.atomic_json(runtime/'play-status.json', dict(state='preparation_failed', detail='Hideyori archive stalled'))
                result = worker.Desktop().snapshot()
                self.assertEqual((result['running'], result['status'], result['detail']), (False, 'preparation_failed', 'Hideyori archive stalled'))
                worker.atomic_json(runtime/'play-status.json', dict(state='enabled', detail='Old session'))
                self.assertEqual(worker.Desktop().snapshot()['status'], 'disabled')

    def test_apply_persists_game_path_before_refreshing_the_form(self):
        # Save to an isolated runtime so this check cannot change the user's selected game.
        # Apply must persist the executable alongside the preset before returning a fresh snapshot.
        # Clearing the path is also a saved choice; neither operation starts gameplay.
        with tempfile.TemporaryDirectory() as folder:
            runtime = Path(folder)
            with patch.object(worker.Desktop, 'location', return_value=runtime), patch.object(worker, 'process_matches', return_value=False):
                desktop = worker.Desktop()
                for executable in (r'C:\Games\Nioh\nioh.exe', ''):
                    result = desktop.apply(dict(self.params, runtime=str(runtime), nioh_exe=executable))
                    self.assertEqual(result['nioh_exe'], executable)
                    self.assertEqual(json.loads((runtime/'trainer-settings.json').read_text(encoding='utf8'))['nioh_exe'], executable)

    def setUp(self):
        # Use checked-in configuration without reading or changing active runtime settings.
        # Each test receives independent dictionaries so failed merges cannot contaminate another case.
        # The controller map supplies logical-button translation, not physical-device acceptance.
        self.preset = json.loads((ROOT/'data/presets/sword-rebuild-1-supported.json').read_text(encoding='utf8'))
        self.calibration = json.loads((ROOT/'data/controller-calibration.json').read_text(encoding='utf8'))
        self.params = dict(preset=self.preset, calibration=self.calibration)

    def test_group_roundtrips_preserve_unrelated_fields(self):
        # Compose every supported group with an independently named and tuned target.
        # Check both values and object ownership so editing a loaded module cannot mutate its source.
        # The result must also pass actual Engine dependency compilation.
        for group, (_, fields) in groups.GROUPS.items():
            target = deepcopy(self.preset); target['name'] = 'My other moveset'
            target['move_settings'] = {'jin_hayabusa.action_0c6e': dict(speed=.5)}
            before = deepcopy(target)
            document = groups.export_group(self.preset, self.calibration, group)
            result = groups.import_group(document, target, self.calibration, group)
            self.assertEqual(target, before)
            self.assertEqual({key: value for key, value in result.items() if key not in fields},
                             {key: value for key, value in before.items() if key not in fields})
            worker.Desktop().preview(dict(self.params, preset=result))
            result['frost_moon']['low'] = None
            self.assertEqual(self.preset['frost_moon']['low'], 'jin_hayabusa.action_0c71')

    def test_chord_group_preserves_logical_buttons_across_controllers(self):
        # Transfer only the custom chord from DS4 to XInput button namespaces.
        # Keep the destination's Frost bindings and tuning independent of that transfer.
        # Compare logical buttons rather than coincidentally equal raw bit masks.
        source = deepcopy(worker.DEFAULT_PRESET)
        target_calibration = dict(device=dict(backend='xinput',slot=0),controller_slot=0)
        target = worker.trainer.remap_preset(self.preset, self.calibration, target_calibration)
        result = groups.import_group(groups.export_group(source, self.calibration, 'chord'), target, target_calibration, 'chord')
        for field in ('modifier_mask','trigger_mask'):
            self.assertEqual(game_button_mask(self.calibration['device'], source[field], self.calibration.get('button_map')),
                             game_button_mask(target_calibration['device'], result[field]))
        self.assertEqual(result['frost_moon'], target['frost_moon'])

    def test_group_cannot_smuggle_unrelated_settings_or_mutate_on_conflict(self):
        # A group file is an exact field contract, not a general preset patch.
        # Cross-group requirements are validated after copying, so rejection cannot change the draft.
        # Version booleans and mismatched groups must not pass as compatible documents.
        document = groups.export_group(self.preset, self.calibration, 'frost')
        for mutation in ('field','version','group'):
            bad = deepcopy(document)
            if mutation == 'field': bad['bindings']['move_settings'] = {}
            elif mutation == 'version': bad['schema_version'] = True
            else: bad['group'] = 'chord'
            with self.assertRaises(ValueError): groups.import_group(bad, self.preset, self.calibration, 'frost')
        target = deepcopy(self.preset); target['low_heavy'] = None; target['skill_bindings'] = []
        before = deepcopy(target)
        skills = groups.export_group(self.preset, self.calibration, 'skills')
        with self.assertRaises(ValueError): groups.import_group(skills, target, self.calibration, 'skills')
        self.assertEqual(target, before)

    def test_broken_saved_preset_opens_as_unsaved_baseline_without_writing(self):
        # Reproduce a corrupt saved file without using the user's runtime folder.
        # Recovery must preserve those bytes and make a valid editable draft available.
        # Missing preset files also translate the shipped baseline to the saved controller.
        with tempfile.TemporaryDirectory() as folder:
            runtime = Path(folder); path = runtime/'controller-binding.json'; path.write_text('{broken',encoding='utf8')
            with patch.object(worker.Desktop, 'location', return_value=runtime):
                result = worker.Desktop().snapshot()
            self.assertTrue(result['load_warning'])
            self.assertEqual(path.read_text(encoding='utf8'), '{broken')
            self.assertEqual(len(list(runtime.iterdir())), 1)
            worker.validate_preset(result['preset'])
            missing = runtime/'missing'; missing.mkdir()
            calibration = dict(device=dict(backend='xinput',slot=0),controller_slot=0)
            (missing/'controller-calibration.json').write_text(json.dumps(calibration), encoding='utf8')
            with patch.object(worker.Desktop, 'location', return_value=missing):
                restored = worker.Desktop().snapshot()
            self.assertEqual(restored['preset']['modifier_mask'], 0x100)
            self.assertEqual(restored['preset']['trigger_mask'], 0x400)
            self.assertFalse(restored['load_warning'])

    def test_add_override_selects_a_free_compilable_slot(self):
        # The old Add button duplicated Tiger Sprint already bound in Any stance.
        # Seed through production compilation and ensure the original draft stays untouched.
        # Eight occupied entries fail cleanly without silently deleting another binding.
        original = deepcopy(worker.DEFAULT_PRESET)
        result = worker.Desktop().add_override(dict(self.params, preset=original))
        self.assertEqual(len(result['skill_bindings']), len(original['skill_bindings'])+1)
        worker.Desktop().preview(dict(self.params, preset=result))
        self.assertEqual(original, worker.DEFAULT_PRESET)
        full = deepcopy(self.preset); full['stance_holds'] = dict(low=None,mid=None,high=None)
        full['skill_bindings'] = [dict(source=source,stance=stance,move='okatsu.charged_rush')
                                 for source in ('tiger_sprint','dodge_attack','guard_light') for stance in ('low','mid','high')][:8]
        with self.assertRaisesRegex(ValueError, 'eight override slots'):
            worker.Desktop().add_override(dict(self.params, preset=full))
        bad = deepcopy(self.calibration); bad['controller_slot'] = True
        with self.assertRaisesRegex(ValueError, 'Controller slot'):
            worker.Desktop().validate(dict(self.params, calibration=bad))
