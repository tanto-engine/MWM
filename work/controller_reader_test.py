"""Fake backend regressions: no game process or real controller access."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "outputs" / "boss-probe"))
from controller_reader import ControllerReader, WinMMBackend


class Backend:
    absent_codes = {1167}
    def __init__(self, name="winmm"):
        self.name = name
        self.value = (1167, None)
        self.reads = 0
    def slots(self): return range(2)
    def read(self, slot):
        self.reads += 1
        return self.value if slot == 0 else (1167, None)
    def describe(self, slot): return {"button_labels": "uncalibrated"}
    def state(self, buttons=0, x=32767, pov=65535):
        self.value = 0, dict(buttons=buttons, pov=pov, axes={"x": x})


class Clock:
    now = 0.0
    def __call__(self): return self.now


class Tests(unittest.TestCase):
    def setup_reader(self, name="winmm"):
        self.backend, self.clock = Backend(name), Clock()
        self.reader = ControllerReader([self.backend], self.clock)
    def inputs(self): return [e for e in self.reader.poll() if e["kind"] == "input"]

    def test_initial_and_disconnect_recovery_have_unknown_edges(self):
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
        class FakeDLL:
            def __init__(self):
                self.caps_calls = []
                self.position_calls = []
                self.position_code = 0
                self.capability_code = 0
            def joyGetNumDevs(self): return 32
            def joyGetDevCapsW(self, slot, caps, size):
                self.caps_calls.append(slot)
                return self.capability_code if slot == 0 else 165
            def joyGetPosEx(self, slot, state):
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


if __name__ == "__main__":
    unittest.main()
