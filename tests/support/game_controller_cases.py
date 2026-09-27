# Offline regression cases for native controller observations, logical mappings and press-to-bind.
# Fixtures isolate game/process effects; these checks do not establish gameplay acceptance.
# Loaded by the existing Engine test entrypoints through Test-Offline.ps1; see CODE_GUIDE.md.
import ctypes as C
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'runtime'), str(ROOT/'runtime')]
import game_controller as controller
from controller_reader import ControllerReader
from gestures import ControllerGesture

DEVICE = dict(backend='winmm', slot=0, manufacturer=0x054c, product=0x09cc, name='DS4 fixture')


class GameInputTests(unittest.TestCase):
    def setUp(self):
        # Create an owned 128-byte trace buffer and the saved DS4 mapping.
        # Expose a fixed QPC frequency and replace only the observer clock.
        # Native input decoding can be tested without a controller or shared game mapping.
        self.buffer = C.create_string_buffer(128)
        self.trace = SimpleNamespace(address=C.addressof(self.buffer), header=lambda: (
            # Expose the fixture trace's 1000-Hz performance-counter frequency.
            # Return the timing header without opening shared memory.
            # Input staleness checks must compare timestamps in the correct units.
            {'frequency':1000}
        ))
        self.backend = controller.GameController(self.trace, {'device':DEVICE, 'lb_mask':16})
        self.clock = patch.object(controller.time, 'perf_counter', return_value=1.0)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def sample(self, sequence=2, qpc=1000, slot=0, buttons=0, connected=None):
        # Publish one four-slot XInput snapshot into owned trace memory.
        # Write sequence, QPC, connection codes, masks, axes and packets in ABI order.
        # Corrupt publication and ambiguous-device cases must reach the real decoder.
        codes = [1167]*4
        for index in [slot] if connected is None else connected:
            codes[index] = 0
        masks = [0]*4
        masks[slot] = buttons
        raw = controller.INPUT.pack(sequence, qpc, *codes, *masks, *([0]*8), *([1]*4))
        C.memmove(self.trace.address+64, raw, len(raw))

    def test_odd_zero_and_torn_sequence_never_emit_input(self):
        # Reject zero, odd and torn native input sequence markers.
        # Publish uncommitted markers and change the marker during a snapshot copy.
        # The native-input adapter must reject every incoherent publication before emitting buttons.
        for sequence in (0, 1, 3):
            self.sample(sequence)
            self.assertEqual(self.backend.read(0), (1237, None))
        self.sample()
        string_at = C.string_at
        def torn(address, size):
            # Change the sequence marker immediately after copying a snapshot.
            # Return the prechange bytes while the consumer sees a newer marker on recheck.
            # A torn read must be rejected even when the copied payload looked complete.
            raw = string_at(address, size)
            C.c_int64.from_address(address).value = 4
            return raw
        with patch.object(controller.C, 'string_at', side_effect=torn):
            self.assertEqual(self.backend.read(0), (1237, None))

    def test_stale_future_and_multiple_pad_samples_disconnect(self):
        # Disconnect stale, future-dated and ambiguous multiple-pad snapshots.
        # Vary the native snapshot timestamp and number of simultaneously connected pads.
        # Old, impossible or ambiguous input cannot be treated as a trusted current controller.
        for stamp in (899, 750, 749, 1001):
            self.sample(qpc=stamp)
            self.assertEqual(self.backend.read(0), (1167, None))
        for connected in ([], [0,1], [0,1,2,3]):
            self.sample(connected=connected)
            self.assertEqual(self.backend.read(0), (1167, None))

    def test_xinput_lb_b_maps_to_saved_ds4_masks(self):
        # Translate native LB and B into the saved DS4 logical mask space.
        # Publish standard XInput LB/B bits through the saved DS4 calibration.
        # The engine must preserve the established 16/4 logical mapping without recalibration.
        self.sample(buttons=0x2100)
        code, state = self.backend.read(0)
        self.assertEqual((code, state['buttons']), (0, 20))
        self.assertEqual(controller.saved_buttons({'backend':'xinput'}, 0x2100, 0, 0), 0x2100)
        with self.assertRaises(ValueError):
            controller.saved_buttons(dict(DEVICE, product=1), 0x2100, 0, 0)

    def test_slot_replacement_does_not_complete_another_pads_gesture(self):
        # Prevent a new XInput slot from completing another controller's gesture.
        # Switch the connected XInput slot during a pending gesture.
        # Device replacement must emit disconnect and require neutral rather than inherit the first pad's press.
        reader = ControllerReader(backends=[self.backend], clock=lambda: (
            # Freeze observation time for the XInput slot-replacement scenario.
            # Return the timestamp matching the owned native sample.
            # Device identity changes must be isolated from unrelated sample expiry.
            1.0
        ))
        gate = ControllerGesture({'device':DEVICE, 'lb_mask':16},
                             {'device':DEVICE, 'lb_mask':16, 'circle_mask':4, 'hold_seconds':.25}, 1000)
        for sequence, slot, buttons, now in ((2,0,0,1000), (4,0,0x100,1010), (6,1,0x2100,1020)):
            self.sample(sequence, slot=slot, buttons=buttons)
            for event in reader.poll():
                gate.process(event, now)
        self.assertFalse(gate.fields(2000)['armed'], 'A different XInput pad completed the prior pad chord')

    def test_game_input_uses_saved_quarter_second_tap_hold_threshold(self):
        # Preserve the saved quarter-second tap-hold threshold on native game input.
        # Feed native input snapshots into the existing Circle gesture at the 250-ms boundary.
        # Transport adaptation must preserve the working Charged Rush versus Leaping Slash timing.
        for hold in (False, True):
            backend = controller.GameController(self.trace, {'device':DEVICE, 'lb_mask':16})
            reader = ControllerReader(backends=[backend], clock=lambda:(
                # Freeze observation time for the saved tap/hold integration case.
                # Use the same origin as the owned input snapshots.
                # The configured 250-ms boundary must be driven by explicit gesture ticks.
                1.0
            ))
            gate = ControllerGesture({'device':DEVICE, 'lb_mask':16},
                                 {'device':DEVICE, 'lb_mask':16, 'circle_mask':4, 'hold_seconds':.25}, 1000)
            self.sample(2, buttons=0)
            for event in reader.poll(): gate.process(event, 1000)
            self.sample(4, buttons=0x2100)
            for event in reader.poll(): gate.process(event, 1100)
            self.assertFalse(gate.fields(1349)['armed'])
            if hold:
                self.assertEqual((gate.fields(1350)['armed'], gate.variant), (True, 1))
            else:
                self.sample(6, buttons=0x100)
                for event in reader.poll(): gate.process(event, 1200)
                self.assertEqual((gate.fields(1201)['armed'], gate.variant), (True, 0))


    def test_saved_mapping_compiles_to_model_independent_buttons(self):
        # Compile saved bindings into controller-model-independent logical buttons.
        # Translate the saved device-specific masks into the native logical button representation.
        # Runtime input must remain portable without changing the user's persisted bindings.
        import copy
        calibration = {'device':DEVICE,'lb_mask':16}
        binding = {'device':DEVICE,'lb_mask':16,'circle_mask':4,'hold_seconds':.25}
        originals = copy.deepcopy((calibration,binding))
        profile, compiled = controller.game_binding(calibration,binding)
        self.assertEqual((compiled['modifier_mask'],compiled['trigger_mask']),(0x100,0x2000))
        self.assertEqual(profile['device'],controller.GAME_DEVICE)
        self.assertEqual((calibration,binding),originals)
        xbox = {'device':controller.GAME_DEVICE,'lb_mask':0x100}
        _, native = controller.game_binding(xbox,dict(compiled))
        self.assertEqual(native['trigger_mask'],0x2000)
        self.assertEqual(controller.binding_buttons(DEVICE)['Circle / B'],4)
        self.assertEqual(controller.binding_buttons(controller.GAME_DEVICE)['Circle / B'],0x2000)

    def test_packet_reset_requires_reconnect_neutral(self):
        # Require reconnect neutral after the native packet counter resets.
        # Reset a connected controller's packet progression while the chord is held.
        # A new stream generation must not complete an old charge until neutral rearming occurs.
        self.sample()
        self.backend.read(0)
        raw = bytearray(C.string_at(self.trace.address+64,64))
        import struct
        # Packet counters begin at byte 48 of the input payload, after all four
        # slots' connection codes, button masks and trigger-axis values.
        struct.pack_into('<I',raw,48,0)
        C.memmove(self.trace.address+64,bytes(raw),64)
        self.assertEqual(self.backend.read(0),(1167,None))

    def test_triggers_compile_in_both_saved_namespaces(self):
        # Keep trigger bindings equivalent in XInput and saved DS4 layouts.
        # Translate both saved representations through the production logical-button mapping.
        # A hardware namespace difference must not change which Nioh control the binding means.
        self.assertEqual(controller.game_button_mask(DEVICE,64),0x400)
        self.assertEqual(controller.game_button_mask(DEVICE,128),0x800)
        self.assertEqual(controller.saved_buttons(controller.GAME_DEVICE,0,128,127),0x400)
        self.assertEqual(controller.saved_buttons(controller.GAME_DEVICE,0,127,128),0x800)

    def test_explicit_slot_never_falls_back_to_another_pad(self):
        # Ensure selecting a particular controller does not silently accept another connected pad.
        # Present observations for the available slots while the selected slot is unavailable.
        # Explicit selection must remain explicit across connection changes.
        backend=controller.GameController(self.trace,{'device':DEVICE,'controller_slot':1})
        self.sample(slot=1,buttons=0x2100,connected=[0,1])
        self.assertEqual(backend.read(0)[1]['buttons'],20)
        self.sample(slot=0,buttons=0x2100,connected=[0])
        self.assertEqual(backend.read(0),(1167,None))

    def test_capture_requires_release_single_press_and_reconnect_release(self):
        # Require release followed by one deliberate input during press-to-bind.
        # Feed held buttons, chords and reconnect events through the same capture state machine used by the trainer.
        # Only a clean single press may complete capture, and reconnecting must require release again.
        capture=controller.BindingCapture({'device':controller.GAME_DEVICE})
        def event(buttons,edge='previous_observation',kind='input'):
            # Build one synthetic input observation for the capture state-machine test.
            # Keep device identity fixed while the caller varies buttons and event kind.
            # This supplies data directly and never sends a controller press to Windows or Nioh.
            return dict(kind=kind,backend='xinput',slot=0,buttons=buttons,
                        axes={'lt':0,'rt':0},edge_basis=edge)
        self.assertIsNone(capture.process(event(0x100,'unknown')))
        self.assertIsNone(capture.process(event(0x2000)))
        self.assertIsNone(capture.process(event(0)))
        self.assertEqual(capture.process(event(0x2000))['mask'],0x2000)
        capture.reset()
        capture.process(event(0))
        self.assertIsNone(capture.process(event(0x2100)))
        self.assertIsNone(capture.process(event(0x2000)))
        capture.process(event(0))
        capture.process(event(0,kind='input_unavailable'))
        self.assertIsNone(capture.process(event(0x2000,'unknown')))
        capture.process(dict(controller.GAME_DEVICE,kind='input_device'))
        capture.process(event(0))
        self.assertEqual(capture.process(event(0x100))['logical_mask'],0x100)

    def test_calibrated_winmm_layout_and_unknown_modes(self):
        # Accept an explicit valid WinMM calibration while rejecting unsupported layouts.
        # Exercise malformed mappings and controller backend identities.
        # A controller's name alone must not authorize an assumed button layout.
        device=dict(DEVICE,product=1)
        mapping={'16':0x100,'4':0x2000}
        self.assertEqual(controller.game_button_mask(device,4,mapping),0x2000)
        self.assertEqual(controller.saved_buttons(device,0x2100,0,0,mapping),20)
        self.assertEqual(controller.binding_buttons(device,mapping)['Circle / B'],4)
        with self.assertRaises(ValueError): controller.binding_buttons(device)
        for invalid in ({'3':0x100},{'4':0x100,'16':0x100},{'4':0x10000}):
            with self.assertRaises(ValueError): controller.binding_buttons(device,invalid)
        with self.assertRaises(ValueError): controller.binding_buttons({'backend':'hid'})

    def test_selection_and_capture_preserve_logical_masks(self):
        # Check the conversion between saved controller selection and logical binding results.
        # Exercise selection bounds and the capture result's saved/logical masks.
        # The same physical choice must remain recognizable after crossing the native observation interface.
        for value in (-1,4,True,'0'):
            with self.assertRaises(ValueError): controller.controller_selection({'controller_slot':value})
        calibration={'device':DEVICE,'lb_mask':16,'controller_slot':2}
        profile,_=controller.game_binding(calibration,dict(calibration,circle_mask=64))
        self.assertEqual(controller.controller_selection(profile),3)
        capture=controller.BindingCapture({'device':controller.GAME_DEVICE})
        base=dict(kind='input',backend='xinput',slot=0,buttons=0,pov=None,axes={'lt':127,'rt':0})
        self.assertIsNone(capture.process(base))
        self.assertIsNone(capture.process(dict(base,slot=1,axes={'lt':128,'rt':0})))
        self.assertEqual(capture.process(dict(base,axes={'lt':128,'rt':0}))['logical_mask'],0x400)

    def test_capture_uses_saved_mask_from_the_native_observer(self):
        # Translate game-facing controller observations back into the saved calibration namespace.
        # Feed a native-observer input and inspect the captured raw and logical identities.
        # Saving the game's bit directly would corrupt bindings for layouts such as DS4/WinMM.
        capture=controller.BindingCapture({'device':DEVICE})
        reader=ControllerReader(backends=[self.backend],clock=lambda: (
            # Give the controller fixture a fixed monotonic time.
            # Deterministic timestamps keep connection and edge assertions independent of test execution speed.
            # This fake clock does not change Windows or game time.
            1.0
        ),rescan_seconds=.1)
        results=[]
        for sequence,buttons in ((2,0x2000),(4,0),(6,0x2000)):
            self.sample(sequence,buttons=buttons)
            for event in reader.poll():
                result=capture.process(event)
                if result: results.append(result)
        self.assertEqual(results,[dict(mask=4,logical_mask=0x2000,label='Circle / B')])

    def test_capture_rejects_an_unmapped_game_button_in_a_chord(self):
        # Reject a chord containing a game button missing from a partial calibration.
        # Do not let translation erase the unknown extra button and leave an apparently valid single press.
        # A complete release and supported single input remain necessary for binding.
        calibration={'device':dict(DEVICE,product=1),'button_map':{'4':0x2000}}
        backend=controller.GameController(self.trace,calibration)
        capture=controller.BindingCapture(calibration)
        reader=ControllerReader(backends=[backend],clock=lambda: (
            # Give the controller fixture a fixed monotonic time.
            # Deterministic timestamps keep connection and edge assertions independent of test execution speed.
            # This fake clock does not change Windows or game time.
            1.0
        ))
        for sequence,buttons in ((2,0),(4,0xA000)):
            self.sample(sequence,buttons=buttons)
            for event in reader.poll():
                self.assertIsNone(capture.process(event),'Unmapped Y must prevent capturing B+Y as B')
