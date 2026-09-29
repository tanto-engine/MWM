# Offline regression cases for tap/hold/chord recognition and stale or interrupted input.
# Fixtures isolate game/process effects; these checks do not establish gameplay acceptance.
# Loaded by the existing Engine test entrypoints through Test-Offline.ps1; see CODE_GUIDE.md.
import json, sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'runtime'))
from gestures import ControllerGesture
FIXTURES=ROOT/'tests/native/fixtures'
C=json.loads((FIXTURES/'controller-calibration.json').read_text())
B=json.loads((FIXTURES/'controller-binding.json').read_text())
B = dict(B, hold_seconds=.45)  # Fixed boundary fixture; runtime preference is configurable.

class Gestures(unittest.TestCase):
    def make(self):
        # Create the saved Circle gesture and establish its device identity.
        # Feed a neutral initial observation before returning the recognizer.
        # Tap/hold tests must begin armed rather than exploit an unknown startup edge.
        g=ControllerGesture(C,B,1000)
        g.process(dict(kind='input_device',**C['device']),100)
        self.input(g,0,101,True)
        return g
    def input(self,g,buttons,t,unknown=False):
        # Deliver a chosen raw button mask and QPC tick to ControllerGesture.
        # Mark the edge as observed or unknown according to the fixture parameter.
        # Startup snapshots and real presses must remain distinguishable.
        return g.process(dict(kind='input',backend='winmm',slot=0,buttons=buttons,
                              edge_basis='unknown' if unknown else 'previous_observation'),t)
    def test_tap_latches_after_release_and_expires(self):
        # Latch a released tap once and expire it at the pending-command deadline.
        # Press and release Circle before the hold threshold, then advance past expiry.
        # A tap needs release recognition but cannot remain queued indefinitely.
        g=self.make();self.input(g,20,200);self.input(g,16,250)
        self.assertEqual((g.fields(260)['armed'],g.variant,g.fields(260)['held']),(True,0,False))
        self.assertFalse(g.fields(651)['armed'])
    def test_extra_button_cancels_without_release_tap(self):
        # An extra shoulder must not turn the configured chord into another attack.
        # Cover adding RB before and during a pending hold, then releasing it first.
        # Only a fresh neutral-to-chord press may arm a later gesture.
        for during in (False,True):
            g=self.make()
            if during:self.input(g,20,150)
            self.input(g,52,200);self.input(g,20,220);self.input(g,0,230)
            self.assertFalse(g.fields(700)['armed'])
            self.input(g,20,800);self.input(g,0,820)
            self.assertTrue(g.fields(821)['armed'])

    def test_hold_fires_once_no_extra_tap(self):
        # Emit one hold action without a second tap on release.
        # Hold the chord through 250 ms, continue holding, then release.
        # One hold must produce one Leaping Slash and no trailing Charged Rush tap.
        g=self.make();self.input(g,20,200)
        self.assertFalse(g.fields(649)['armed']);self.assertTrue(g.fields(650)['armed'])
        self.assertEqual(g.variant,1);g.dispatched()
        self.assertFalse(g.fields(660)['armed']);self.input(g,16,900)
        self.assertFalse(g.fields(901)['armed']);self.assertEqual(g.chord_sequence,1)
    def test_repeated_circle_while_lb_stays_held(self):
        # Allow another Circle gesture while LB remains continuously held.
        # Release and repress Circle while maintaining the modifier.
        # A fresh Circle gesture must work without requiring a redundant LB release.
        g=self.make()
        for t in (200,400,600):
            self.input(g,20,t);self.input(g,16,t+50)
            self.assertTrue(g.fields(t+51)['armed']);g.dispatched()
        self.assertEqual(g.chord_sequence,3)
    def test_start_held_requires_release(self):
        # Require neutral input after attaching to an already-held chord.
        # Attach while the chord is already held, then supply neutral and a fresh press.
        # An initial state snapshot must not impersonate the player's intended activation.
        g=self.make();self.input(g,20,200,True)
        self.assertFalse(g.fields(1000)['armed'])
        self.input(g,16,1001);self.input(g,20,1002);self.input(g,16,1050)
        self.assertTrue(g.fields(1051)['armed'])
    def test_disconnect_cancels_charge_and_pending(self):
        # Cancel held and pending gestures on controller disconnection.
        # Disconnect while charging or after a tap has been queued.
        # An old gesture must not survive loss of its physical input stream.
        g=self.make();self.input(g,20,200)
        g.process(dict(kind='input_unavailable',backend='winmm',slot=0),300)
        self.assertFalse(g.fields(900)['armed'])
    def test_lb_release_cancels_hold_without_tap(self):
        # Cancel a hold when LB is released without manufacturing a tap.
        # Release the modifier before Circle finishes its gesture.
        # Modifier loss must cancel the charge without converting it into an unintended tap.
        g=self.make();self.input(g,20,200);self.input(g,4,220);self.input(g,0,230)
        self.assertFalse(g.fields(231)['armed'])
    def test_release_at_threshold_is_charge_once(self):
        # Resolve release exactly at the hold threshold as one charged action.
        # Release Circle exactly at the configured 250-ms boundary.
        # Boundary ordering must select one hold result without double dispatch.
        g=self.make();self.input(g,20,200);self.input(g,0,650)
        self.assertEqual((g.variant,g.chord_sequence),(1,1))


class TriggerString(unittest.TestCase):
    def input(self, gate, buttons, tick, lt=0, rt=0, valid=True):
        gate.process(dict(kind='input', backend='winmm', slot=0, buttons=buttons,
                          axes=dict(lt=lt, rt=rt), edge_basis='previous_observation'), tick, valid)
        return gate.fields(tick)

    def test_bound_string_hold_keeps_followups_armed_until_release(self):
        gate = ControllerGesture(C, dict(B, variants=[None, 2]), 1000, string_variant=2)
        gate.process(dict(kind='input_device', **C['device']), 100)
        self.input(gate, 0, 101)
        self.input(gate, 20, 200)
        start = gate.fields(700)
        self.assertEqual((start['variant'], start['armed'], start['held'], start['latched']), (2, True, True, 0))
        gate.dispatched()
        self.assertTrue(gate.fields(710)['held'])
        self.assertFalse(self.input(gate, 16, 720)['held'])

    def test_unbound_triggers_do_not_start_a_hidden_string(self):
        gate = ControllerGesture(C, dict(B, variants=[None, None]), 1000, string_variant=2)
        gate.process(dict(kind='input_device', **C['device']), 100)
        self.input(gate, 0, 101)
        self.assertFalse(self.input(gate, 0, 200, 255, 255)['armed'])
        self.assertEqual(gate.chord_sequence, 0)

    def test_context_loss_cancels_held_string(self):
        gate = ControllerGesture(C, dict(B, variants=[None, 2]), 1000, string_variant=2)
        gate.process(dict(kind='input_device', **C['device']), 100)
        self.input(gate, 0, 101)
        self.input(gate, 20, 200)
        self.assertTrue(gate.fields(700)['held'])
        self.assertFalse(self.input(gate, 20, 701, valid=False)['held'])
