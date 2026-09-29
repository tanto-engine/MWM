"""Recorded sword candidates must stay traceable and unplayable until reviewed."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('sword_dataset_validation', ROOT / 'dataset/validate.py')
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class RecordingIntakeTests(unittest.TestCase):
    def test_unmapped_candidates_cannot_become_playable_by_catalogue_edit(self):
        # Verify the imported names and immutable archive references are present.
        # Turn one candidate selectable in a temporary catalogue to prove the gate rejects it.
        # This cannot establish behavior on William; the source action is deliberately unset.
        records = validator.load_dataset(ROOT / 'dataset')
        path = ROOT / 'data/moves.json'
        self.assertEqual(validator.verify_catalogue(records, path),
                         sum(move.get('mapping_status') == 'unmapped' for move in records.values()))
        self.assertTrue(any('recorded_take_missing' in move['blocked_reasons'] for move in records.values()
                            if move.get('mapping_status') == 'unmapped'))
        catalogue = json.loads(path.read_text(encoding='utf8'))
        candidate = next(move for move in catalogue['moves'] if move['id'].startswith('sword.'))
        candidate['implementation']['selectable'] = True
        with tempfile.TemporaryDirectory() as folder:
            altered = Path(folder) / 'moves.json'
            altered.write_text(json.dumps(catalogue), encoding='utf8')
            with self.assertRaises(ValueError):
                validator.verify_catalogue(records, altered)
