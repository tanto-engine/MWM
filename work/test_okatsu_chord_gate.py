"""Pure offline tests: no controller, process, or injected code access."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "outputs" / "okatsu-prototype"))
from chord_gate import ChordGate


class ChordGateTests(unittest.TestCase):
    def setUp(self):
        self.gate = ChordGate()

    def update(self, lb, lt, context_valid=True, connected=True):
        return self.gate.update(lb, lt, context_valid, connected)

    def arm(self):
        self.assertFalse(self.update(False, 0.0))

    def test_lb_then_lt_triggers_once(self):
        self.arm()
        self.assertFalse(self.update(True, 0.0))
        self.assertTrue(self.update(True, 0.6))
        self.assertFalse(self.update(True, 1.0))

    def test_lt_then_lb_triggers_once(self):
        self.arm()
        self.assertFalse(self.update(False, 0.7))
        self.assertTrue(self.update(True, 0.7))
        self.assertFalse(self.update(True, 0.7))

    def test_simultaneous_press_and_sustained_hold(self):
        self.arm()
        self.assertTrue(self.update(True, 1.0))
        for _ in range(100):
            self.assertFalse(self.update(True, 1.0))

    def test_releasing_only_lb_does_not_rearm(self):
        self.arm()
        self.assertTrue(self.update(True, 0.9))
        self.assertFalse(self.update(False, 0.9))
        self.assertFalse(self.update(True, 0.9))

    def test_releasing_only_lt_does_not_rearm(self):
        self.arm()
        self.assertTrue(self.update(True, 0.9))
        self.assertFalse(self.update(True, 0.0))
        self.assertFalse(self.update(True, 0.9))

    def test_nonoverlapping_releases_do_not_rearm(self):
        self.arm()
        self.assertTrue(self.update(True, 0.9))
        self.assertFalse(self.update(False, 0.9))
        self.assertFalse(self.update(True, 0.0))
        self.assertFalse(self.update(True, 0.9))

    def test_both_released_rearms_for_next_chord(self):
        self.arm()
        self.assertTrue(self.update(True, 0.9))
        self.assertFalse(self.update(False, 0.4))
        self.assertTrue(self.update(True, 0.6))

    def test_lt_hysteresis_preserves_press_until_release_threshold(self):
        self.arm()
        for axis in (0.59, 0.5, 0.599):
            self.assertFalse(self.update(True, axis))
        self.assertFalse(self.update(False, 0.6))
        # LT already crossed its press threshold; 0.5 still counts as held.
        self.assertTrue(self.update(True, 0.5))
        for axis in (0.59, 0.61, 0.41, 0.6):
            self.assertFalse(self.update(True, axis))
        self.assertFalse(self.update(False, 0.41))
        self.assertFalse(self.update(True, 0.7))
        self.assertFalse(self.update(False, 0.4))
        self.assertTrue(self.update(True, 0.6))

    def test_lt_release_threshold_clears_hysteresis(self):
        self.arm()
        self.assertFalse(self.update(False, 0.7))
        self.assertFalse(self.update(False, 0.4))
        self.assertFalse(self.update(True, 0.5))
        self.assertTrue(self.update(True, 0.6))

    def test_startup_held_or_ambiguous_axis_requires_both_released(self):
        for lb, lt in ((True, 1.0), (True, 0.0), (False, 1.0), (False, 0.5)):
            with self.subTest(lb=lb, lt=lt):
                self.gate = ChordGate()
                self.assertFalse(self.update(lb, lt))
                self.assertFalse(self.update(True, 1.0))
                self.arm()
                self.assertTrue(self.update(True, 1.0))

    def test_disconnect_and_reconnect_held_require_fresh_release(self):
        self.arm()
        self.assertFalse(self.update(False, 0.0, connected=False))
        self.assertFalse(self.update(True, 0.9, connected=True))
        self.assertFalse(self.update(False, 0.9))
        self.assertFalse(self.update(True, 0.9))
        self.arm()
        self.assertTrue(self.update(True, 0.9))

    def test_invalid_context_and_return_held_require_fresh_release(self):
        self.arm()
        self.assertFalse(self.update(False, 0.0, context_valid=False))
        self.assertFalse(self.update(True, 0.9, context_valid=True))
        self.arm()
        self.assertTrue(self.update(True, 0.9))

    def test_invalid_axis_resets_and_cannot_fire(self):
        for axis in (float("nan"), float("inf"), -float("inf"), -0.01, 1.01,
                     10 ** 1000, -(10 ** 1000), None, "0.8", True):
            with self.subTest(axis=axis):
                self.arm()
                self.assertFalse(self.update(True, axis))
                self.assertFalse(self.update(True, 0.9))
                self.arm()
                self.assertTrue(self.update(True, 0.9))

    def test_invalid_logical_types_reset(self):
        for lb, context, connected in ((1, True, True), (True, "yes", True), (True, True, 1)):
            with self.subTest(lb=lb, context=context, connected=connected):
                self.arm()
                self.assertFalse(self.update(lb, 0.9, context, connected))
                self.assertFalse(self.update(True, 0.9))


if __name__ == "__main__":
    unittest.main(verbosity=2)
