"""Recorded route identity and compilation; these checks do not certify gameplay."""
import copy
import json
from pathlib import Path
import unittest
from move_imports import read_import_manifest, check_import_topology
from prepare_session import configured_replacements, compiled_move_settings

ROOT=Path(__file__).resolve().parents[2]


class IshidaTests(unittest.TestCase):
    def test_all_five_routes_keep_repetitions_stances_and_timing_override(self):
        preset=json.loads((ROOT/'mwm/data/presets/sword-ishida.json').read_text())
        moves=configured_replacements(preset)['moves']
        settings=compiled_move_settings(preset,moves)
        self.assertEqual(len(moves),19)
        expected={'double_slash':[0xC5B,0xC5B,0xC5C,0xC58], 'three_hit':[0xC71,0xC72,0xC6E],
                  'spin_ender':[0xC5C,0xC58,0xC7A], 'spin_opener':[0xC78,0xC5B,0xC5C,0xC58],
                  'five_hit':[0xC6C,0xC6D,0xC71,0xC72,0xC6E]}
        for binding in preset['skill_bindings']:
            index=next(i for i,m in enumerate(moves) if m['id']==binding['move']);keys=[]
            while index>=0:
                move=moves[index];keys.append(move['key'])
                self.assertLessEqual(len(keys),5)
                self.assertEqual(move['replacement']['player_key'],{'low':0xCF5,'mid':0xC7A,'high':0xCB7}[binding['stance']])
                self.assertEqual(settings[index]['input_family'],1 if binding['source']=='light_attack' else 2)
                if move['key']==0xC71:self.assertEqual(move['timing'],91030)
                index=move['next_variant']
            self.assertEqual(keys,expected[binding['move'].split('.')[1][:-2]])

    def test_aliases_reject_changed_source_and_cyclic_routes(self):
        manifest=read_import_manifest(ROOT/'mwm/data/imports/ishida_mitsunari.json')
        moves=copy.deepcopy(manifest['moves']);moves[1]['motion']+=1
        with self.assertRaises(ValueError):check_import_topology(moves,None)
        moves=copy.deepcopy(manifest['moves']);moves[1]['next_variant']=0
        with self.assertRaisesRegex(ValueError,'cycle'):check_import_topology(moves,None)
