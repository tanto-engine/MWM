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
    def test_disabled_preset_cannot_emit_any_okatsu_binding(self):
        # Exercise the inactive preset with the legacy string entry still available.
        # Attempt both Circle gestures and the two-trigger chord after neutral input.
        # Preserving imported moves must not preserve their disabled bindings.
        g = ControllerGesture(C, dict(B, variants=[None, None], string_enabled=False), 1000, 2)
        g.process(dict(kind='input_device', **C['device']), 100)
        for t, buttons, lt, rt in ((101,0,0,0), (200,20,0,0), (250,16,0,0),
                                   (300,20,0,0), (800,20,0,0), (850,0,0,0),
                                   (900,0,255,255), (1500,0,255,255)):
            self.assertFalse(self.input(g, lt, rt, t, buttons)['armed'])
        self.assertEqual(g.chord_sequence, 0)

    def make(self):
        # Create the trigger-string recognizer with entry variant two.
        # Register the saved device without inventing a neutral trigger observation.
        # Each test must explicitly establish neutral before arming the chain.
        g=ControllerGesture(C,B,1000,string_variant=2)
        g.process(dict(kind='input_device',**C['device']),100)
        return g

    def input(self,g,lt,rt,t,buttons=0,**extra):
        # Feed both trigger axes and optional lifecycle fields to the recognizer.
        # Return published gesture fields at the same deterministic QPC tick.
        # Tests can correlate held-state cancellation with the exact queued variant.
        g.process(dict(kind='input',backend='winmm',slot=0,buttons=buttons,
                       axes=dict(lt=lt,rt=rt),**extra),t)
        return g.fields(t)

    def test_partial_release_finishes_current_move_and_requires_both_neutral(self):
        # Cancel later string links when either trigger releases and require both neutral.
        # Release either trigger mid-string and repress it while the other remains held.
        # The current move may finish, but the cancelled chain cannot resume until both release.
        for released in ((0,255),(255,0)):
            with self.subTest(released=released):
                g=self.make()
                self.input(g,0,0,101)
                start=self.input(g,255,255,200)
                self.assertEqual((start['variant'],start['latched'],start['held'],start['armed']),(2,0,True,True))
                g.dispatched()
                self.assertTrue(self.input(g,255,255,700)['held'])
                self.assertFalse(g.fields(700)['armed'])
                self.assertFalse(self.input(g,*released,701)['held'])
                self.assertFalse(self.input(g,255,255,702)['armed'])
                self.assertEqual(g.chord_sequence,1)
                self.input(g,0,0,703)
                self.assertTrue(self.input(g,255,255,704)['armed'])
                self.assertEqual(g.chord_sequence,2)

    def test_reconnect_or_context_loss_while_held_never_restarts_chain(self):
        # Prevent reconnect or context recovery from restarting a held string.
        # Lose connection or gameplay context and return with triggers still held.
        # A new valid context must require neutral instead of reviving stale string intent.
        for interruption in ('reconnect','context','unknown'):
            with self.subTest(interruption=interruption):
                g=self.make();self.input(g,0,0,101);self.input(g,255,255,200)
                if interruption=='reconnect':
                    g.process(dict(kind='input_unavailable',backend='winmm',slot=0),201)
                    g.process(dict(kind='input_device',**C['device']),202)
                elif interruption=='context':
                    g.process(dict(kind='input',backend='winmm',slot=0,buttons=0,axes=dict(lt=255,rt=255)),201,False)
                else:
                    self.input(g,255,255,201,edge_basis='unknown')
                self.assertFalse(self.input(g,255,255,203)['armed'])
                self.assertFalse(g.fields(203)['held'])
                self.input(g,0,0,204)
                self.assertTrue(self.input(g,255,255,205)['armed'])

    def test_threshold_noise_expiry_and_baseline_gesture(self):
        # Separate trigger threshold noise and expiry from the baseline tap-hold gesture.
        # Vary trigger noise, queued-string expiry and the original Circle chord.
        # String recognition must respect thresholds without replacing the working tap/hold binding.
        g=self.make()
        self.assertFalse(self.input(g,255,255,101)['armed'])
        self.input(g,0,0,102)
        self.assertFalse(self.input(g,127,255,200)['armed'])
        self.assertTrue(self.input(g,128,255,201)['armed'])
        self.assertTrue(self.input(g,97,97,202)['held'])
        self.assertFalse(self.input(g,96,97,203)['held'])
        self.input(g,0,0,204)
        self.input(g,255,255,205)
        self.assertFalse(g.fields(605)['armed'])
        self.assertTrue(g.fields(605)['held'])
        self.input(g,0,0,606)
        self.input(g,0,0,700,buttons=20)
        tap=self.input(g,0,0,750,buttons=16)
        self.assertEqual((tap['armed'],tap['variant'],tap['latched']),(True,0,1))
        g.dispatched()
        self.input(g,0,0,800,buttons=20)
        hold=g.fields(1250)
        self.assertEqual((hold['armed'],hold['variant']),(True,1))
