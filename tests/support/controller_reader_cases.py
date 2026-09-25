import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "outputs" / "boss-probe"))
from controller_reader import ControllerReader, WinMMBackend


class Backend:
    absent_codes = {1167}
    def __init__(self, name="winmm"):
        # Start a named controller backend with no connected device.
        # Retain a configurable read result and poll counter.
        # Reconnect tests must begin with absence rather than an invented neutral pad.
        self.name = name
        self.value = (1167, None)
        self.reads = 0
    def slots(self):
        # Expose two possible controller slots to the scanner.
        # Only the first slot can be populated by this fixture.
        # Absent-slot throttling can be checked alongside active-device polling.
        return range(2)
    def read(self, slot):
        # Return the configured input only for slot zero.
        # Count all reads and report native disconnection for the other slot.
        # Tests can detect excessive rescans without depending on physical controllers.
        self.reads += 1
        return self.value if slot == 0 else (1167, None)
    def describe(self, slot):
        # Label the fixture's button meanings as uncalibrated.
        # Return capability metadata without assigning semantic controls.
        # Raw controller discovery must not fabricate a usable LB/Circle mapping.
        return {"button_labels": "uncalibrated"}
    def state(self, buttons=0, x=32767, pov=65535):
        # Connect slot zero with a chosen button, axis and POV snapshot.
        # Replace the backend result rather than accumulating synthetic edges.
        # The production reader must derive changes from consecutive observations.
        self.value = 0, dict(buttons=buttons, pov=pov, axes={"x": x})


class Clock:
    now = 0.0
    def __call__(self):
        # Provide the controller scanner's manually advanced monotonic time.
        # Return the fixture clock value without sleeping.
        # Reconnect and rescan deadlines remain deterministic.
        return self.now


class Tests(unittest.TestCase):
    def setup_reader(self, name="winmm"):
        # Combine a fresh backend and clock with the production ControllerReader.
        # Keep the backend name selectable for both WinMM and XInput cases.
        # The same edge invariants must hold independently of controller transport.
        self.backend, self.clock = Backend(name), Clock()
        self.reader = ControllerReader([self.backend], self.clock)
    def inputs(self):
        # Select raw input events from one production reader poll.
        # Leave device and error events available through direct polls in other checks.
        # Button-edge assertions should not depend on unrelated status event ordering.
        return [e for e in self.reader.poll() if e["kind"] == "input"]

    def test_initial_and_disconnect_recovery_have_unknown_edges(self):
        # Mark initial and reconnect samples as having unknown button edges.
        # Connect, disconnect and reconnect with button state already present.
        # The first observation of each stream must not claim a previous-state press edge.
        self.setup_reader()
        self.backend.state(buttons=4)
        first = self.inputs()[0]
        self.assertIsNone(first["pressed_mask"])
        self.assertIsNone(first["released_mask"])
        self.backend.value = 1167, None
        lost = self.reader.poll()
        self.assertEqual([e["kind"] for e in lost], ["input_unavailable"])
        self.assertIsNone(lost[0]["released_mask"])
        self.assertEqual(self.reader.status()["valid_slots"]["winmm"], [])
        self.assertEqual(self.reader.poll(), [])
        self.backend.state(buttons=8)
        self.clock.now = 2
        recovered = self.inputs()[0]
        self.assertIsNone(recovered["pressed_mask"])
        self.assertIsNone(recovered["released_mask"])
        self.assertEqual(self.reader.status()["button_edges"], 0)

    def test_both_backends_preserve_edges_and_pov_despite_axis_jitter(self):
        # Keep real button and POV changes visible despite small axis jitter.
        # Replay button/POV transitions plus small analog noise through WinMM and XInput fixtures.
        # Filtering axis jitter must never suppress discrete button or directional changes.
        for name in ("winmm", "xinput"):
            with self.subTest(name=name):
                self.setup_reader(name)
                self.backend.state()
                self.inputs()
                self.backend.state(x=32768)
                self.assertEqual(self.inputs(), [])
                self.backend.state(buttons=3, x=32768)
                event = self.inputs()[0]
                self.assertEqual((event["pressed_mask"], event["released_mask"]), (3, 0))
                self.assertEqual(event["buttons_down"], [1, 2])
                self.backend.state(buttons=2, pov=9000)
                event = self.inputs()[0]
                self.assertEqual((event["pressed_mask"], event["released_mask"]), (0, 1))
                self.backend.state(buttons=2, pov=18000)
                event = self.inputs()[0]
                self.assertEqual(event["pov"], 18000)
                self.assertEqual(self.reader.status()["button_edges"], 3)

    def test_absent_slots_rescan_without_spam_or_errors(self):
        # Rescan absent slots without repeated errors or fabricated input.
        # Advance the scan clock with absent slots and then make the primary slot available.
        # Disconnected capacity must be retried without emitting repeated errors or excessive polling.
        self.setup_reader()
        self.assertEqual(self.reader.poll(), [])
        self.assertEqual(self.backend.reads, 2)
        self.clock.now = 1.9
        self.backend.state()
        self.assertEqual(self.reader.poll(), [])
        self.assertEqual(self.backend.reads, 2)
        self.clock.now = 2
        self.assertEqual(len(self.inputs()), 1)
        self.assertEqual(self.backend.reads, 4)
        self.assertEqual(self.reader.status()["unexpected_error_events"], 0)

    def test_unexpected_error_logs_only_changes_and_recovery_resets_it(self):
        # Report changed backend failures once and reset state on recovery.
        # Repeat one backend failure, change its code and restore valid input.
        # Status deduplication must retain meaningful changes while avoiding repeated identical reports.
        self.setup_reader()
        self.backend.value = 165, None
        self.assertEqual(len(self.reader.poll()), 1)
        self.clock.now = 2
        self.assertEqual(self.reader.poll(), [])
        self.assertEqual(self.reader.status()["unexpected_error_events"], 1)
        self.backend.state()
        self.clock.now = 4
        self.inputs()
        self.backend.value = 165, None
        self.reader.poll()
        self.assertEqual(self.reader.status()["unexpected_error_events"], 2)

    def test_winmm_capabilities_filter_empty_slots_but_keep_active_read_errors(self):
        # Use device capabilities to skip empty WinMM slots while retaining active read errors.
        # Expose 32 possible WinMM slots but capabilities for only one and vary its read result.
        # Enumeration filtering must not conceal errors from a device already considered active.
        class FakeDLL:
            def __init__(self):
                # Track WinMM capability and position queries independently.
                # Allow their native result codes to vary without changing the slot inventory.
                # An active read failure must not be hidden as an unavailable capability slot.
                self.caps_calls = []
                self.position_calls = []
                self.position_code = 0
                self.capability_code = 0
            def joyGetNumDevs(self):
                # Report the full 32-slot WinMM capacity.
                # Keep actual availability controlled by the separate capability callback.
                # Enumeration must filter absent devices rather than poll every possible slot forever.
                return 32
            def joyGetDevCapsW(self, slot, caps, size):
                # Expose capabilities only for slot zero and log each request.
                # Return the configured capability result for that slot and absence elsewhere.
                # Tests can distinguish cached enumeration from repeated active input reads.
                self.caps_calls.append(slot)
                return self.capability_code if slot == 0 else 165
            def joyGetPosEx(self, slot, state):
                # Return the configured position-read result and record its slot.
                # Avoid filling input fields because these cases exercise error classification.
                # A failed active read must still reach the reader's observable error path.
                self.position_calls.append(slot)
                return self.position_code
        backend = WinMMBackend.__new__(WinMMBackend)
        backend.dll = FakeDLL()
        backend._caps = {}
        backend.capability_codes = {}
        clock = Clock()
        reader = ControllerReader([backend], clock)
        reader.poll()
        self.assertEqual(backend.dll.caps_calls, list(range(16)))
        self.assertEqual(backend.dll.position_calls, [0])
        self.assertEqual(reader.status()["unexpected_error_events"], 0)
        backend.dll.capability_code = 165
        backend.dll.position_code = 165
        clock.now = 2
        events = reader.poll()
        self.assertEqual(backend.dll.position_calls, [0, 0])
        self.assertEqual(events[0]["kind"], "input_unavailable")
        self.assertEqual(events[0]["code"], 165)
        self.assertFalse(events[0]["expected_absence"])
        self.assertEqual(reader.status()["unexpected_error_events"], 1)
