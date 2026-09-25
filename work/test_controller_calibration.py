"""Offline calibration/gate tests; controller_reader is never imported."""
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "outputs" / "okatsu-prototype"))
import calibrate_controller as cal


DEVICE = dict(backend="winmm", slot=0, name="Fixture controller", manufacturer=1, product=2,
              num_buttons=14, num_axes=6, caps_result=0,
              axis_ranges={axis: [0, 65535] for axis in ("x", "y", "z", "r", "u", "v")})


def evidence(neutral=0, full=65535, lt_button=0x40):
    result = {}
    for phase, _ in cal.PHASES:
        axes = dict(x=32767, y=32767, z=32767, r=32767, u=0, v=neutral)
        mask = 0
        if phase in ("lb", "both"):
            mask |= 0x10
        if phase in ("lt", "both"):
            mask |= lt_button
            axes["v"] = full
        result[phase] = [dict(buttons=mask, pov=65535, axes=copy.deepcopy(axes)) for _ in range(20)]
    return result


class CalibrationTests(unittest.TestCase):
    def test_positive_polarity_and_secondary_trigger_button(self):
        profile = cal.infer_calibration(evidence(), DEVICE)
        self.assertEqual(profile["lb_mask"], 0x10)
        self.assertEqual(profile["lt"]["axis"], "v")
        self.assertEqual(profile["lt"]["accompanying_button_mask"], 0x40)
        self.assertEqual(profile["device"], DEVICE)
        self.assertEqual(cal.normalize_lt(0, profile["lt"]), 0)
        self.assertEqual(cal.normalize_lt(65535, profile["lt"]), 1)

    def test_inverted_and_centered_trigger_polarities(self):
        for neutral, full in ((65535, 0), (32767, 0), (32767, 65535)):
            with self.subTest(neutral=neutral, full=full):
                profile = cal.infer_calibration(evidence(neutral, full, lt_button=0), DEVICE)
                self.assertEqual(cal.normalize_lt(neutral, profile["lt"]), 0)
                self.assertEqual(cal.normalize_lt(full, profile["lt"]), 1)
                self.assertAlmostEqual(cal.normalize_lt((neutral + full) / 2, profile["lt"]), 0.5)

    def test_xinput_ranges_are_explicit_and_inference_remains_prompt_based(self):
        phases = {}
        for phase, _ in cal.PHASES:
            axes = dict(lt=255 if phase in ("lt", "both") else 0, rt=0, lx=0, ly=0, rx=0, ry=0)
            phases[phase] = [dict(buttons=0x100 if phase in ("lb", "both") else 0,
                                   pov=None, axes=axes.copy()) for _ in range(20)]
        profile = cal.infer_calibration(phases, dict(backend="xinput", slot=0))
        self.assertEqual(profile["lb_mask"], 0x100)
        self.assertEqual(profile["lt"]["axis"], "lt")
        self.assertEqual(profile["lt"]["advertised_range"], [0, 255])

    def test_multiple_changed_axes_are_ambiguous(self):
        phases = evidence()
        for phase in ("lt", "both"):
            for sample in phases[phase]:
                sample["axes"]["u"] = 65535
        with self.assertRaisesRegex(ValueError, "one clearly changed LT axis"):
            cal.infer_calibration(phases, DEVICE)

    def test_missing_or_partial_trigger_motion_is_rejected(self):
        for full in (0, 10000, 45000):
            with self.subTest(full=full), self.assertRaises(ValueError):
                cal.infer_calibration(evidence(full=full), DEVICE)

    def test_ambiguous_or_inconsistent_button_masks_are_rejected(self):
        for phase, mask in (("lb", 0x30), ("lt", 0x10), ("lt", 0x60),
                            ("both", 0x10), ("neutral", 1), ("release", 1)):
            phases = evidence()
            for sample in phases[phase]:
                sample["buttons"] = mask
            with self.subTest(phase=phase, mask=mask), self.assertRaises(ValueError):
                cal.infer_calibration(phases, DEVICE)

    def test_release_and_both_phase_axis_validation(self):
        for phase, value in (("release", 20000), ("lb", 20000), ("both", 45000)):
            phases = evidence()
            for sample in phases[phase]:
                sample["axes"]["v"] = value
            with self.subTest(phase=phase), self.assertRaises(ValueError):
                cal.infer_calibration(phases, DEVICE)

    def test_unstable_axis_or_too_few_samples_rejected(self):
        phases = evidence()
        phases["lt"][0]["axes"]["v"] = 30000
        with self.assertRaisesRegex(ValueError, "Unstable"):
            cal.infer_calibration(phases, DEVICE)
        with self.assertRaisesRegex(ValueError, "Too few"):
            cal.infer_calibration(dict(evidence(), lb=[]), DEVICE)

    def test_invalid_axis_cannot_normalize(self):
        mapping = cal.infer_calibration(evidence(), DEVICE)["lt"]
        for value in (None, True, "0", float("nan"), float("inf"), -1, 65536, 10 ** 1000):
            with self.subTest(value=value):
                self.assertIsNone(cal.normalize_lt(value, mapping))


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.adapter = cal.CalibratedChord(cal.infer_calibration(evidence(), DEVICE))

    def device(self, **changes):
        return self.adapter.process(dict(DEVICE, kind="input_device", **changes), context_valid=True)

    def state(self, buttons, axis, unknown=False, context_valid=True):
        return self.adapter.process(dict(kind="input", backend="winmm", slot=0,
            observed_monotonic=1.0, buttons=buttons, axes={"v": axis},
            edge_basis="unknown" if unknown else "previous_observation"), context_valid=context_valid)

    def test_initial_held_releases_then_fires_once(self):
        self.device()
        self.assertFalse(self.state(0x50, 65535, unknown=True)["chord_candidate"])
        self.assertFalse(self.state(0, 0)["chord_candidate"])
        self.assertTrue(self.state(0x50, 65535)["chord_candidate"])
        self.assertFalse(self.state(0x50, 65535)["chord_candidate"])

    def test_reconnect_held_requires_compatible_device_and_release(self):
        self.device()
        self.state(0, 0, unknown=True)
        self.adapter.process(dict(kind="input_unavailable", backend="winmm", slot=0), context_valid=True)
        self.assertFalse(self.state(0x50, 65535)["chord_candidate"])
        self.device()
        self.assertFalse(self.state(0x50, 65535, unknown=True)["chord_candidate"])
        self.state(0, 0)
        self.assertTrue(self.state(0x50, 65535)["chord_candidate"])

    def test_changed_device_capabilities_fail_closed(self):
        event = dict(DEVICE, kind="input_device")
        event["product"] = 99
        self.assertFalse(self.adapter.process(event, context_valid=True)["accepted"])
        self.state(0, 0, unknown=True)
        self.assertFalse(self.state(0x50, 65535)["chord_candidate"])

    def test_unseen_device_and_other_streams_cannot_fire(self):
        self.state(0, 0, unknown=True)
        self.assertFalse(self.state(0x50, 65535)["chord_candidate"])
        self.device()
        self.state(0, 0, unknown=True)
        self.assertIsNone(self.adapter.process(dict(kind="input", backend="xinput", slot=0,
                         buttons=0x50, axes={"v": 65535}), context_valid=True))

    def test_context_loss_and_invalid_axis_disarm(self):
        self.device()
        self.state(0, 0, unknown=True)
        self.adapter.process(dict(kind="context_changed"), context_valid=False)
        self.assertFalse(self.state(0x50, 65535)["chord_candidate"])
        self.state(0, 0)
        self.assertFalse(self.state(0x50, None)["chord_candidate"])
        self.assertFalse(self.state(0x50, 65535)["chord_candidate"])
        self.state(0, 0)
        self.assertTrue(self.state(0x50, 65535)["chord_candidate"])


class CollectionTests(unittest.TestCase):
    def test_cue_file_requires_exact_phase_json(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "cue.json"
            self.assertFalse(cal.cue_matches(path, "neutral"))
            for content in ('{', '"neutral"', '{"phase":"NEUTRAL"}', '{"phase":"lb"}', '{"phase":true}'):
                path.write_text(content)
                self.assertFalse(cal.cue_matches(path, "neutral"))
            path.write_text('{"phase":"neutral"}', encoding="utf-8-sig")
            self.assertTrue(cal.cue_matches(path, "neutral"))

    def test_wait_deadline_keeps_polling_and_records_failed_status(self):
        for total, wait, reason in ((10, 0.05, "Timed out waiting"), (0.04, 10, "Total calibration deadline")):
            clock = [0.0]
            calls = [0]
            class Reader:
                def poll(self):
                    calls[0] += 1
                    return [dict(kind="fixture_poll", observed_monotonic=clock[0])]
            def sleep(seconds):
                clock[0] += seconds
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as td, \
                    patch.object(cal.time, "perf_counter", side_effect=lambda: clock[0]), \
                    patch.object(cal.time, "sleep", side_effect=sleep), \
                    patch("builtins.print"), patch.object(cal, "cue_matches", return_value=False):
                status = Path(td) / "status.json"
                stream = io.StringIO()
                with self.assertRaisesRegex(ValueError, reason):
                    cal.collect(Reader(), "winmm", 0, 1, 1, stream, cue_file="fixture",
                                status_file=status, total_seconds=total, wait_seconds=wait)
                saved = json.loads(status.read_text())
                self.assertEqual(saved["state"], "failed")
                self.assertEqual(saved["completed_phases"], [])
                self.assertGreater(calls[0], 0)
                self.assertTrue(all(json.loads(row)["stage"] == "waiting_for_cue"
                                    for row in stream.getvalue().splitlines()))

    def test_stale_previous_cue_never_starts_next_phase(self):
        clock = [0.0]
        neutral = evidence()["neutral"][0]
        class Reader:
            first = True
            def poll(self):
                events = []
                if self.first:
                    events.append(dict(DEVICE, kind="input_device", observed_monotonic=clock[0]))
                    self.first = False
                return events + [dict(neutral, kind="input", backend="winmm", slot=0,
                                      observed_monotonic=clock[0])]
        def sleep(seconds):
            clock[0] += seconds
        with tempfile.TemporaryDirectory() as td, \
                patch.object(cal.time, "perf_counter", side_effect=lambda: clock[0]), \
                patch.object(cal.time, "sleep", side_effect=sleep), patch("builtins.print"), \
                patch.object(cal, "cue_matches", side_effect=lambda path, phase: phase == "neutral"):
            status = Path(td) / "status.json"
            stream = io.StringIO()
            with self.assertRaisesRegex(ValueError, "waiting for lb cue"):
                cal.collect(Reader(), "winmm", 0, 1, 1, stream, cue_file="fixture",
                            status_file=status, total_seconds=10, wait_seconds=0.05)
            saved = json.loads(status.read_text())
            self.assertEqual(saved["completed_phases"], ["neutral"])
            self.assertEqual(saved["phase"], "lb")
            rows = [json.loads(row) for row in stream.getvalue().splitlines()]
            self.assertEqual([row["phase"] for row in rows if row["kind"] == "phase_cue"], ["neutral"])
            self.assertFalse(any(row["kind"] == "calibration_sample" and row["phase"] == "lb" for row in rows))

    def test_disconnect_or_device_change_aborts_calibration(self):
        for failure in (dict(kind="input_unavailable", backend="winmm", slot=0),
                        dict(DEVICE, kind="input_device", product=99)):
            class Reader:
                def poll(self):
                    return [dict(DEVICE, kind="input_device"), failure]
            with self.subTest(failure=failure), patch("builtins.print"), self.assertRaises(ValueError):
                cal.collect(Reader(), "winmm", 0, 1, 1, io.StringIO())

    def test_bounded_prompted_phases_preserve_raw_evidence(self):
        phases = evidence()
        clock = [0.0]
        current = ["neutral"]

        class Reader:
            first = True

            def poll(self):
                events = []
                if self.first:
                    events.append(dict(DEVICE, kind="input_device", observed_monotonic=clock[0]))
                    self.first = False
                events.append(dict(phases[current[0]][0], kind="input", backend="winmm",
                                   slot=0, observed_monotonic=clock[0]))
                return events

        def prompt(message, **kwargs):
            current[0] = message.split(":", 1)[0].lower()

        def sleep(seconds):
            clock[0] += seconds

        stream = io.StringIO()
        with patch.object(cal.time, "perf_counter", side_effect=lambda: clock[0]), \
                patch.object(cal.time, "sleep", side_effect=sleep), patch("builtins.print", side_effect=prompt):
            profile = cal.collect(Reader(), "winmm", 0, 1, 1, stream)
        rows = [json.loads(line) for line in stream.getvalue().splitlines()]
        self.assertEqual(profile["lb_mask"], 0x10)
        self.assertGreaterEqual(clock[0], 10)
        self.assertLess(clock[0], 10.1)
        self.assertEqual({r["phase"] for r in rows}, {p for p, _ in cal.PHASES})
        self.assertTrue(any(r["kind"] == "calibration_sample" for r in rows))


if __name__ == "__main__":
    unittest.main(verbosity=2)
