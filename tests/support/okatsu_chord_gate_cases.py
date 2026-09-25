from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "outputs" / "okatsu-prototype"))
from chord_gate import ChordGate


class ChordGateTests(unittest.TestCase):
    def setUp(self):
        # Start each logical chord scenario with a fresh gate.
        # Preserve the production startup requirement for a neutral observation.
        # Prior tests must not leave a chord armed or partially held.
        self.gate = ChordGate()

    def update(self, lb, lt, context_valid=True, connected=True):
        # Feed explicit LB, trigger, context and connection values to the gate.
        # Keep defaults limited to valid gameplay and a connected input stream.
        # Each test can isolate one hysteresis or rearming boundary.
        return self.gate.update(lb, lt, context_valid, connected)

    def arm(self):
        # Establish both controls released before testing a new chord.
        # Assert the neutral observation itself produces no activation.
        # Initial input state must never be mistaken for a player press.
        self.assertFalse(self.update(False, 0.0))

    def test_lb_then_lt_triggers_once(self):
        # Recognize one chord when LB precedes the trigger.
        # Arm neutral, press LB first and then cross the trigger press threshold.
        # Modifier-first input order must produce exactly one chord activation.
        self.arm()
        self.assertFalse(self.update(True, 0.0))
        self.assertTrue(self.update(True, 0.6))
        self.assertFalse(self.update(True, 1.0))

    def test_lt_then_lb_triggers_once(self):
        # Recognize one chord when the trigger precedes LB.
        # Arm neutral, press the trigger first and then LB.
        # Trigger-first input order must obey the same one-activation contract.
        self.arm()
        self.assertFalse(self.update(False, 0.7))
        self.assertTrue(self.update(True, 0.7))
        self.assertFalse(self.update(True, 0.7))

    def test_simultaneous_press_and_sustained_hold(self):
        # Emit one event for a simultaneous press followed by a sustained hold.
        # Press both controls in one observation and keep supplying held samples.
        # Continuous holding must not create repeated rising edges.
        self.arm()
        self.assertTrue(self.update(True, 1.0))
        for _ in range(100):
            self.assertFalse(self.update(True, 1.0))

    def test_releasing_only_lb_does_not_rearm(self):
        # Keep the chord disarmed when only LB is released.
        # Release and repress LB while the trigger stays above its release threshold.
        # One control cycling cannot reuse an already-consumed chord.
        self.arm()
        self.assertTrue(self.update(True, 0.9))
        self.assertFalse(self.update(False, 0.9))
        self.assertFalse(self.update(True, 0.9))

    def test_releasing_only_lt_does_not_rearm(self):
        # Keep the chord disarmed when only the trigger is released.
        # Release and repress the trigger while LB remains held.
        # Rearming requires a shared neutral observation rather than either independent release.
        self.arm()
        self.assertTrue(self.update(True, 0.9))
        self.assertFalse(self.update(True, 0.0))
        self.assertFalse(self.update(True, 0.9))

    def test_nonoverlapping_releases_do_not_rearm(self):
        # Require both controls neutral together rather than separate release samples.
        # Release each control at different times without observing both neutral together.
        # The gate must not combine unrelated release moments into a fresh chord permission.
        self.arm()
        self.assertTrue(self.update(True, 0.9))
        self.assertFalse(self.update(False, 0.9))
        self.assertFalse(self.update(True, 0.0))
        self.assertFalse(self.update(True, 0.9))

    def test_both_released_rearms_for_next_chord(self):
        # Rearm only after both controls have returned to neutral.
        # Observe both controls neutral between two complete chord presses.
        # A real release cycle must restore one activation without requiring recalibration.
        self.arm()
        self.assertTrue(self.update(True, 0.9))
        self.assertFalse(self.update(False, 0.4))
        self.assertTrue(self.update(True, 0.6))

    def test_lt_hysteresis_preserves_press_until_release_threshold(self):
        # Use trigger hysteresis to retain a press above the release threshold.
        # Move the trigger within the gap between press and release thresholds.
        # Analog noise below the press threshold must not prematurely release a held trigger.
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
        # Clear trigger hysteresis at the verified release threshold.
        # Cross the release threshold after a valid trigger press.
        # A genuine release must clear held state so a later fresh chord can arm.
        self.arm()
        self.assertFalse(self.update(False, 0.7))
        self.assertFalse(self.update(False, 0.4))
        self.assertFalse(self.update(True, 0.5))
        self.assertTrue(self.update(True, 0.6))

    def test_startup_held_or_ambiguous_axis_requires_both_released(self):
        # Require neutral input after held startup or ambiguous axis evidence.
        # Attach with held controls or an intermediate trigger value.
        # Unknown initial state must become neutral before the first accepted chord.
        for lb, lt in ((True, 1.0), (True, 0.0), (False, 1.0), (False, 0.5)):
            with self.subTest(lb=lb, lt=lt):
                self.gate = ChordGate()
                self.assertFalse(self.update(lb, lt))
                self.assertFalse(self.update(True, 1.0))
                self.arm()
                self.assertTrue(self.update(True, 1.0))

    def test_disconnect_and_reconnect_held_require_fresh_release(self):
        # Reject held reconnect input until a fresh release is observed.
        # Disconnect an armed gate and return with both controls pressed.
        # The replacement input stream must not inherit the earlier armed gesture.
        self.arm()
        self.assertFalse(self.update(False, 0.0, connected=False))
        self.assertFalse(self.update(True, 0.9, connected=True))
        self.assertFalse(self.update(False, 0.9))
        self.assertFalse(self.update(True, 0.9))
        self.arm()
        self.assertTrue(self.update(True, 0.9))

    def test_invalid_context_and_return_held_require_fresh_release(self):
        # Reject held context recovery until a fresh release is observed.
        # Suspend gameplay context and restore it while the chord remains held.
        # Context recovery must reset gesture intent before accepting another activation.
        self.arm()
        self.assertFalse(self.update(False, 0.0, context_valid=False))
        self.assertFalse(self.update(True, 0.9, context_valid=True))
        self.arm()
        self.assertTrue(self.update(True, 0.9))

    def test_invalid_axis_resets_and_cannot_fire(self):
        # Reset the chord when a trigger value is invalid.
        # Feed malformed, nonfinite and out-of-range trigger values.
        # A failed observation must disarm rather than normalize into a valid press.
        for axis in (float("nan"), float("inf"), -float("inf"), -0.01, 1.01,
                     10 ** 1000, -(10 ** 1000), None, "0.8", True):
            with self.subTest(axis=axis):
                self.arm()
                self.assertFalse(self.update(True, axis))
                self.assertFalse(self.update(True, 0.9))
                self.arm()
                self.assertTrue(self.update(True, 0.9))

    def test_invalid_logical_types_reset(self):
        # Reset the chord when logical input types are not valid.
        # Supply nonboolean logical controls and incompatible context values.
        # Loose truthiness must not allow malformed events to activate an imported skill.
        for lb, context, connected in ((1, True, True), (True, "yes", True), (True, True, 1)):
            with self.subTest(lb=lb, context=context, connected=connected):
                self.arm()
                self.assertFalse(self.update(lb, 0.9, context, connected))
                self.assertFalse(self.update(True, 0.9))
