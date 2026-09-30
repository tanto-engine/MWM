"""Every selectable or tunable sword move needs an input and behavior explanation."""
import json
from pathlib import Path
import unittest

from engine_config import move_capabilities

ROOT = Path(__file__).resolve().parents[1]


class MoveHelpTests(unittest.TestCase):
    def test_menu_names_do_not_fall_back_to_internal_ids(self):
        self.assertEqual([move['id'] for move in move_capabilities()['moves'] if move['name']==move['id']], [])

    def test_every_runtime_move_and_source_has_specific_help(self):
        help = json.loads((ROOT/'data/move-help.json').read_text(encoding='utf8'))
        capabilities = move_capabilities()
        self.assertEqual(set(help['moves']), {move['id'] for move in capabilities['moves']})
        self.assertEqual(set(help['sources']), {source['id'] for source in capabilities['native_sources']})
        for collection, key in (('moves', 'moves'), ('sources', 'native_sources')):
            for row in capabilities[key]:
                self.assertEqual({field: row[field] for field in ('input', 'description')},
                                 {field: help[collection][row['id']][field] for field in ('input', 'description')})
        for collection in ('moves', 'sources'):
            for identifier, row in help[collection].items():
                with self.subTest(identifier=identifier):
                    self.assertTrue(row['input'].strip())
                    self.assertTrue(row['description'].strip())
                    self.assertNotIn('changes this part', row['description'].lower())
