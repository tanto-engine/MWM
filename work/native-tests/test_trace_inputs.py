"""Identity attribution unit checks; no controller or process is opened."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'outputs/okatsu-prototype'))
from trace_inputs import player_identity_matches


class IdentityTests(unittest.TestCase):
    def test_requires_both_observed_pointers_and_valid_owner(self):
        good = dict(actor='0x123000', owner='0x456000', valid_fields=31)
        self.assertTrue(player_identity_matches(good, 0x123000, 0x456000))
        self.assertFalse(player_identity_matches(dict(good, owner='0x789000'), 0x123000, 0x456000))
        self.assertFalse(player_identity_matches(dict(good, actor='0x789000'), 0x123000, 0x456000))
        self.assertFalse(player_identity_matches(dict(good, valid_fields=30), 0x123000, 0x456000))


if __name__ == '__main__':
    unittest.main()
