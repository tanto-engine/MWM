import json, sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'outputs/okatsu-prototype'))
from circle_gesture import CircleGesture
FIXTURES=Path(__file__).resolve().parent/'fixtures'
C=json.loads((FIXTURES/'controller-calibration.json').read_text())
B=json.loads((FIXTURES/'controller-binding.json').read_text())
B = dict(B, hold_seconds=.45)  # Fixed boundary fixture; runtime preference is configurable.

class Gestures(unittest.TestCase):
    def make(self):
        g=CircleGesture(C,B,1000)
        g.process(dict(kind='input_device',**C['device']),100)
        self.input(g,0,101,True)
        return g
    def input(self,g,buttons,t,unknown=False):
        return g.process(dict(kind='input',backend='winmm',slot=0,buttons=buttons,
                              edge_basis='unknown' if unknown else 'previous_observation'),t)
    def test_tap_latches_after_release_and_expires(self):
        g=self.make();self.input(g,20,200);self.input(g,16,250)
        self.assertEqual((g.fields(260)['armed'],g.variant,g.fields(260)['held']),(True,0,False))
        self.assertFalse(g.fields(651)['armed'])
    def test_hold_fires_once_no_extra_tap(self):
        g=self.make();self.input(g,20,200)
        self.assertFalse(g.fields(649)['armed']);self.assertTrue(g.fields(650)['armed'])
        self.assertEqual(g.variant,1);g.dispatched()
        self.assertFalse(g.fields(660)['armed']);self.input(g,16,900)
        self.assertFalse(g.fields(901)['armed']);self.assertEqual(g.chord_sequence,1)
    def test_repeated_circle_while_lb_stays_held(self):
        g=self.make()
        for t in (200,400,600):
            self.input(g,20,t);self.input(g,16,t+50)
            self.assertTrue(g.fields(t+51)['armed']);g.dispatched()
        self.assertEqual(g.chord_sequence,3)
    def test_start_held_requires_release(self):
        g=self.make();self.input(g,20,200,True)
        self.assertFalse(g.fields(1000)['armed'])
        self.input(g,16,1001);self.input(g,20,1002);self.input(g,16,1050)
        self.assertTrue(g.fields(1051)['armed'])
    def test_disconnect_cancels_charge_and_pending(self):
        g=self.make();self.input(g,20,200)
        g.process(dict(kind='input_unavailable',backend='winmm',slot=0),300)
        self.assertFalse(g.fields(900)['armed'])
    def test_lb_release_cancels_hold_without_tap(self):
        g=self.make();self.input(g,20,200);self.input(g,4,220);self.input(g,0,230)
        self.assertFalse(g.fields(231)['armed'])
    def test_release_at_threshold_is_charge_once(self):
        g=self.make();self.input(g,20,200);self.input(g,0,650)
        self.assertEqual((g.variant,g.chord_sequence),(1,1))

if __name__=='__main__': unittest.main()
