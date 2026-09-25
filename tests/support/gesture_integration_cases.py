import copy
import ctypes as C
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'runtime'))
from gestures import ControllerGesture
from run_dispatch import CommandMap

DEVICE = dict(backend='winmm', slot=0, name='owned fixture')
CALIBRATION = dict(device=DEVICE, lb_mask=16)
BINDING = dict(device=DEVICE, lb_mask=16, circle_mask=4, hold_seconds=.45)


class IntegrationReview(unittest.TestCase):
    def make(self):
        # Initialize the baseline Circle binding with the saved device mapping.
        # Supply a neutral button event before testing combined input sequences.
        # Integration cases must distinguish new edges from attachment-time state.
        g = ControllerGesture(CALIBRATION, BINDING, 1000)
        g.process(dict(kind='input_device', **DEVICE), 100)
        self.input(g, 0, 101)
        return g

    def input(self, g, buttons, now, **extra):
        # Deliver a raw button event with explicit previous-observation provenance.
        # Allow tests to add disconnect or context fields to the same event shape.
        # The gesture adapter must cancel pending work when input validity changes.
        g.process(dict(kind='input', backend='winmm', slot=0, buttons=buttons,
                       edge_basis='previous_observation', **extra), now)

    def test_release_both_latches_tap_without_held_requirement(self):
        # Allow a latched tap after both buttons release without requiring held state.
        # Release LB and Circle together after a short valid press.
        # The completed tap must remain dispatchable even though the chord is no longer held.
        g = self.make()
        self.input(g, 20, 200)
        self.input(g, 0, 240)
        f = g.fields(241)
        self.assertEqual((f['armed'], f['held'], f['latched'], f['variant']), (True, False, 1, 0))

    def test_held_charge_expiry_never_refires_and_lb_can_remain_held(self):
        # Prevent an expired hold from firing again while preserving LB reuse.
        # Let a held charge expire, then release and press Circle while retaining LB.
        # Expiry must consume old intent while allowing a genuinely new Circle gesture.
        g = self.make()
        self.input(g, 20, 200)
        self.assertTrue(g.fields(650)['armed'])
        self.assertFalse(g.fields(1050)['armed'])
        self.assertFalse(g.fields(5000)['armed'])
        self.assertEqual(g.chord_sequence, 1)
        self.input(g, 16, 5001)
        self.input(g, 20, 5002)
        self.input(g, 16, 5040)
        self.assertEqual((g.fields(5041)['armed'], g.variant, g.chord_sequence), (True, 0, 2))

    def test_pending_tap_disconnect_and_reconnect_held_require_new_release(self):
        # Require neutral input after a pending tap is interrupted by disconnection.
        # Queue a tap, disconnect and reconnect with the chord held.
        # The replacement stream must not dispatch either the old tap or a fabricated hold.
        g = self.make()
        self.input(g, 20, 200)
        self.input(g, 16, 220)
        g.process(dict(kind='input_unavailable', backend='winmm', slot=0), 221)
        self.assertFalse(g.fields(222)['armed'])
        g.process(dict(kind='input_device', **DEVICE), 300)
        self.input(g, 20, 301)
        self.assertFalse(g.fields(1000)['armed'])
        self.input(g, 16, 1001)
        self.input(g, 20, 1002)
        self.assertTrue(g.fields(1452)['armed'])

    def test_charge_then_lb_release_and_repress_cannot_refire(self):
        # Prevent LB release and repress from reviving an already-fired hold.
        # Fire a hold, cycle LB while Circle remains down and poll again.
        # Modifier cycling must not reuse the already-consumed Circle press.
        g = self.make()
        self.input(g, 20, 200)
        self.assertTrue(g.fields(650)['armed'])
        g.dispatched()
        self.input(g, 4, 700)
        self.input(g, 20, 710)
        self.assertFalse(g.fields(2000)['armed'])
        self.assertEqual(g.chord_sequence, 1)

    def test_variant_pack_preserves_config_and_selects_exact_source_fields(self):
        # Pack the requested move variant without mutating its saved configuration.
        # Pack both baseline gesture variants from the same immutable session configuration.
        # Variant selection must change only the corresponding move fields and preserve shared ownership data.
        cfg = dict(generation=7, player=0x100000, owner=0x200000, vtable=0x300000,
                   banks=[0x400000, 0x500000, 0x600000], descriptor=0x700000,
                   payload=0x800000, key=0xC64, motion=1220,
                   charged=dict(descriptor=0x900000, payload=0xA00000, key=0xC66, motion=1230))
        before = copy.deepcopy(cfg)
        owned = C.create_string_buffer(224)
        command = CommandMap.__new__(CommandMap)
        command.address, command.sequence = C.addressof(owned), 0
        for variant, expected in ((1, cfg['charged']), (0, cfg)):
            command.publish(cfg, heartbeat=1000, edge=900, expires=1200,
                            chord_sequence=variant+1, armed=True, held=False, latched=1, variant=variant)
            self.assertEqual(struct.unpack_from('<QQIi', owned.raw, 64+96),
                             (expected['descriptor'], expected['payload'], expected['key'], expected['motion']))
            self.assertEqual(struct.unpack_from('<II3Q', owned.raw, 64+120), (1, 0, 1, variant, 0))
        self.assertEqual(cfg, before)
