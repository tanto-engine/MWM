"""Sword configuration UI and developer review, using disposable files only."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[2]
MOD=ROOT.parent/'SKM'
sys.path[:0]=[str(MOD),str(MOD/'app'),str(ROOT/'runtime')]
import trainer
from engine_config import DEFAULT_PRESET, validate_preset, atomic_json
from game_controller import BindingCapture
from review_import import review_import


class SwordConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.folder=Path(self.temporary.name)
        atomic_json(self.folder/'controller-calibration.json',json.loads((MOD/'data/controller-calibration.json').read_text()))
        atomic_json(self.folder/'controller-binding.json',DEFAULT_PRESET)
        self.runtime=patch.object(trainer,'RUNTIME',self.folder);self.runtime.start()
        self.root=tk.Tk();self.root.withdraw()
        self.app=trainer.Trainer(self.root,adopt_running=False)

    def tearDown(self):
        self.app.cancel_capture()
        self.root.destroy()
        self.runtime.stop();self.temporary.cleanup()

    def test_baseline_roundtrip_excludes_private_timing_and_preserves_every_override(self):
        self.assertEqual(self.app.form(),DEFAULT_PRESET)
        self.assertFalse(hasattr(self.app,'frost_window'))
        self.assertFalse(hasattr(self.app,'frost_speed'))
        self.assertEqual(len(self.app.binding_table.get_children()),len(DEFAULT_PRESET['skill_bindings']))
        self.assertTrue(self.app.apply())
        self.assertEqual(json.loads((self.folder/'controller-binding.json').read_text()),DEFAULT_PRESET)

    def test_graph_chord_and_speed_survive_apply_load_and_legacy_migration(self):
        preset=copy.deepcopy(DEFAULT_PRESET)
        preset.update(tap_move='jin_hayabusa.action_0c75',chord_stance='high',
            move_settings={'jin_hayabusa.action_0c75':{'speed':1.25}})
        preset['frost_moon']['high']='jin_hayabusa.action_0c75'
        self.app.load_fields(validate_preset(preset))
        self.assertTrue(self.app.apply())
        self.app.load_fields(validate_preset(json.loads((self.folder/'controller-binding.json').read_text())))
        self.assertEqual(self.app.form(),preset)
        legacy=dict(DEFAULT_PRESET,schema_version=7,frost_window_seconds=.5,frost_startup_speed=3)
        legacy.pop('move_settings');legacy.pop('chord_stance')
        self.app.load_fields(validate_preset(legacy))
        self.assertEqual(self.app.form(),DEFAULT_PRESET)

    def test_catalogue_research_rows_never_enter_playable_choices(self):
        imported={move['id'] for move in self.app.capabilities['moves']}
        for choices in (self.app.move_names,self.app.native_choices,self.app.native_move_choices,self.app.frost_choices):
            self.assertTrue(set(choices.values())-{None}<=imported)
        self.assertNotIn('jin_hayabusa.action_0cac',self.app.move_names.values())
        self.assertEqual(set(self.app.source_choices.values()),{source['id'] for source in self.app.capabilities['native_sources']})

    def test_native_editor_replaces_one_context_without_dropping_other_bindings(self):
        preserved=[b for b in DEFAULT_PRESET['skill_bindings'] if (b['source'],b['stance'])!=('tiger_sprint','any')]
        self.app.binding_source.set('Tiger Sprint');self.app.binding_stance.set('any')
        self.app.binding_move.set(next(label for label,identifier in self.app.native_move_choices.items() if identifier=='okatsu.leaping_slash'))
        self.app.set_native_binding()
        result=self.app.form()['skill_bindings']
        self.assertEqual(result[:-1],preserved)
        self.assertEqual(result[-1],dict(source='tiger_sprint',stance='any',move='okatsu.leaping_slash'))
        self.app.binding_stance.set('low');self.app.set_native_binding()
        self.assertEqual(self.app.form()['skill_bindings'],result)
        self.assertIn('overlap',self.app.notice.get())

    def test_invalid_speed_never_replaces_saved_configuration(self):
        label=next(iter(self.app.speed_choices));identifier=self.app.speed_choices[label]
        self.app.speed_choice.set(label);self.app.select_speed();self.app.speed_value.set('nan')
        self.app.set_speed()
        self.assertEqual(float(self.app.speed_fields[identifier].get()),1)
        self.app.speed_value.set('1.5');self.app.set_speed()
        self.assertEqual(self.app.form()['move_settings'][identifier],{'speed':1.5})
        self.assertEqual(json.loads((self.folder/'controller-binding.json').read_text()),DEFAULT_PRESET)

    def test_switch_to_xinput_preserves_logical_controls_and_baseline(self):
        self.app.device_choice.set('XInput controller 3');self.app.choose_controller()
        self.assertEqual((self.app.form()['modifier_mask'],self.app.form()['trigger_mask']),(0x100,0x2000))
        self.assertEqual(self.app.calibration['controller_slot'],2)
        self.assertTrue(self.app.apply())
        self.assertEqual(json.loads((self.folder/'controller-calibration.json').read_text())['controller_slot'],2)
        self.app.baseline()
        self.assertEqual((self.app.form()['modifier_mask'],self.app.form()['trigger_mask']),(0x100,0x2000))

    def test_exported_moveset_remaps_buttons_when_loaded_on_another_controller(self):
        path=self.folder/'export.json'
        with patch('tkinter.filedialog.asksaveasfilename',return_value=str(path)):
            self.app.save()
        saved=json.loads(path.read_text())
        self.assertEqual(saved['kind'],'sword_moveset')
        self.app.device_choice.set('XInput controller 2');self.app.choose_controller()
        with patch('tkinter.filedialog.askopenfilename',return_value=str(path)):
            self.app.load()
        self.assertEqual((self.app.form()['modifier_mask'],self.app.form()['trigger_mask']),(0x100,0x2000))
        self.assertEqual(self.app.calibration['controller_slot'],1)
        self.assertEqual(self.app.form()['skill_bindings'],DEFAULT_PRESET['skill_bindings'])

    def test_press_capture_requires_release_and_commits_only_to_form(self):
        self.app.device_choice.set('XInput controller 1');self.app.choose_controller()
        self.app.capture=BindingCapture(self.app.calibration);self.app.capture_target=self.app.trigger
        events=[dict(kind='input_device',backend='xinput',slot=0),
            dict(kind='input',backend='xinput',slot=0,buttons=0,axes={},pov=None),
            dict(kind='input',backend='xinput',slot=0,buttons=0x8000,axes={},pov=None)]
        self.app.capture_reader=Mock(poll=Mock(return_value=events))
        self.app.poll_capture()
        self.assertEqual(self.app.form()['trigger_mask'],0x8000)
        self.assertIsNone(self.app.capture)
        self.assertEqual(json.loads((self.folder/'controller-binding.json').read_text()),DEFAULT_PRESET)


class SwordImportReviewTests(unittest.TestCase):
    def test_valid_manifest_report_never_promotes_execution_or_gameplay(self):
        report=review_import(MOD/'data/imports/okatsu.json')
        self.assertTrue(report['definition_valid']);self.assertFalse(report['executable']);self.assertFalse(report['gameplay_accepted'])
        self.assertFalse(report['issues']);self.assertTrue(report['requirements'])

    def test_raw_recording_and_unknown_source_need_authored_adapter(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'raw.json';path.write_text(json.dumps(dict(kind='encounter_reconstruction',schema_version=1,boss_id='unreviewed',actions=[])))
            report=review_import(path)
            self.assertFalse(report['definition_valid']);self.assertTrue(report['issues']);self.assertFalse(report['executable'])
            self.assertTrue(any('adapter' in requirement for requirement in report['requirements']))

    def test_missing_resources_and_mismatched_evidence_are_reported(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'reconstruction.json';path.write_text(json.dumps(dict(kind='encounter_reconstruction',schema_version=1,boss_id='maria',actions=[])))
            report=review_import(MOD/'data/imports/okatsu.json',resources=Path(td),evidence=path,reviewed=True)
            self.assertTrue(any('resource profile' in issue for issue in report['issues']))
            self.assertTrue(any('different boss' in issue for issue in report['issues']))
            self.assertFalse(report['executable'])
