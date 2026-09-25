# Dry-run chord logic only; does not read inputs or modify a game.
#
# The caller must supply calibrated logical LB and normalized LT (0..1),
# plus independently established connection and gameplay-context validity.
# Raw WinMM button bits/axes must not be passed without calibration.
import math


class ChordGate:
    # Emit once for LB+LT, after observing both controls released.
    #
    # LT becomes pressed at >=0.6 and stays pressed until <=0.4. Startup,
    # disconnects, invalid input, and invalid context all require a fresh
    # observation with LB released and LT <=0.4 before another trigger.

    PRESS_THRESHOLD = 0.6
    RELEASE_THRESHOLD = 0.4

    def __init__(self):
        # Initialize the research chord detector in a disarmed state.
        # Use the same reset path used after invalid samples.
        # Startup-held controls never count as a new press.
        self.reset()

    def reset(self):
        # Forget prior neutral and trigger-hysteresis observations.
        # Clear both latches without emitting an input event.
        # A later valid release is required before the gate can fire.
        self._armed = False
        self._lt_pressed = False

    def update(self, lb: bool, lt: float, context_valid: bool, connected: bool) -> bool:
        # Detect one calibrated LB-plus-trigger edge.
        # Apply separate press/release thresholds after context and type checks.
        # Trigger noise and reconnects cannot synthesize repeated activation.
        valid_types = (isinstance(lb, bool) and isinstance(context_valid, bool)
                       and isinstance(connected, bool) and isinstance(lt, (int, float))
                       and not isinstance(lt, bool))
        if (not valid_types or not context_valid or not connected
                or not 0.0 <= lt <= 1.0 or not math.isfinite(lt)):
            self.reset()
            return False

        if lt >= self.PRESS_THRESHOLD:
            self._lt_pressed = True
        elif lt <= self.RELEASE_THRESHOLD:
            self._lt_pressed = False

        # Actual release threshold is required, including on the first sample;
        # an uninitialized hysteresis latch is not evidence of LT release.
        if not lb and lt <= self.RELEASE_THRESHOLD:
            self._armed = True
            return False

        if self._armed and lb and self._lt_pressed:
            self._armed = False
            return True
        return False
