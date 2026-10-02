"""Maria's authored presets and evidence, separate from gameplay acceptance."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'runtime'))
from engine_config import validate_preset, FROST_MOVES
from move_imports import read_import_manifest
from nioh_sword import is_recorded_grounded
from prepare_session import configured_replacements, compiled_move_settings


class MariaTests(unittest.TestCase):
    def preset(self, name='sword-maria'):
        return json.loads((ROOT/'mwm/data/presets'/f'{name}.json').read_text())

    def test_presets_compile_stance_and_continuation_ownership(self):
        for name in ('sword-maria', 'sword-maria-dash'):
            preset = validate_preset(self.preset(name))
            moves = configured_replacements(preset)['moves']
            settings = dict(zip((m['id'] for m in moves), compiled_move_settings(preset, moves)))
            self.assertEqual(len(moves), 11)  # Eight Maria phases plus the retained Jin Pulse-test skill.
            for binding in preset['skill_bindings'][:3]:
                manifest = read_import_manifest(ROOT/'mwm/data/imports/maria.json')
                for child in manifest['hold_chains'][binding['move']]:
                    self.assertEqual(settings[child]['input_family'], 2 if binding['source']=='heavy_attack' else 1)
                    move = next(m for m in moves if m['id']==child)
                    self.assertEqual(move['replacement']['player_key'], {'low':0xCF5,'mid':0xC7A,'high':0xCB7}[binding['stance']])

    def test_shared_phases_and_skill_only_slots_reject_bad_bindings(self):
        preset = self.preset()
        preset['skill_bindings'].append(dict(source='heavy_attack', stance='low', move='maria.action_0c8a'))
        with self.assertRaises(ValueError):
            configured_replacements(preset)
        for source in ('guard_strong', 'quick_followup', 'strong_followup'):
            preset = self.preset()
            preset['skill_bindings'][0]['source'] = source
            with self.assertRaises(ValueError):
                validate_preset(preset)
        self.assertNotIn('maria.action_0c80', FROST_MOVES)
        self.assertIn('maria.action_0c89', FROST_MOVES)

    def test_source_signatures_reject_colliding_actions(self):
        manifest = read_import_manifest(ROOT/'mwm/data/imports/maria.json')
        self.assertEqual(len(manifest['moves']), 9)
        self.assertEqual(manifest['hold_chains']['maria.action_0c89'], ['maria.action_0c89'])
        for move in manifest['moves']:
            self.assertTrue(is_recorded_grounded(move))
            for field in ('motion','flags','transition_count','recovery_frame'):
                changed = copy.deepcopy(move)
                changed[field] += 1
                self.assertFalse(is_recorded_grounded(changed))

    def test_selected_capture_steps_match_immutable_archives(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('maria_dataset', ROOT/'mwm/dataset/validate.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        records = module.load_dataset(ROOT/'mwm/dataset')
        selected = {k:v for k,v in records.items() if v['boss_id']=='maria' and v['steps']}
        self.assertEqual(len(selected), 6)
        self.assertEqual(module.verify_evidence(selected, ROOT/'mwm/dataset/evidence'), 6)

    def test_compiler_rejects_havok_file_in_camera_position(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('maria_compiler', ROOT/'mwm/dataset/compile_trial.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        packages = [(b'action', {}), (b'TMG_PACK', {}), (b'G2A_PACK', {}), (b'\x182011-04', {})]
        with patch.object(module, 'observations', return_value={}), \
             patch.object(module, 'asset', side_effect=packages) as asset, patch.object(module, 'write') as write:
            with self.assertRaisesRegex(ValueError, 'camera is not a motion package'):
                module.compile_sources(Path('unused'), 'maria')
            self.assertEqual(asset.call_args.args[-1], 4289)
            write.assert_not_called()
