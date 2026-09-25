import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "outputs" / "okatsu-prototype"))
import calibrate_controller as cal


DEVICE = dict(backend="winmm", slot=0, name="Fixture controller", manufacturer=1, product=2,
              num_buttons=14, num_axes=6, caps_result=0,
              axis_ranges={axis: [0, 65535] for axis in ("x", "y", "z", "r", "u", "v")})


def evidence(neutral=0, full=65535, lt_button=0x40):
    # Build raw samples for each prompted calibration phase.
    # Vary trigger polarity and secondary button reporting while keeping other axes neutral.
    # Inference must derive control meaning from evidence rather than controller-brand guesses.
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
        # Infer a positive trigger axis even when pressing it also changes a button.
        # Infer LB and the positive trigger axis from prompted raw samples that also expose a trigger button.
        # The secondary bit must not confuse the physical modifier mapping.
        profile = cal.infer_calibration(evidence(), DEVICE)
        self.assertEqual(profile["lb_mask"], 0x10)
        self.assertEqual(profile["lt"]["axis"], "v")
        self.assertEqual(profile["lt"]["accompanying_button_mask"], 0x40)
        self.assertEqual(profile["device"], DEVICE)
        self.assertEqual(cal.normalize_lt(0, profile["lt"]), 0)
        self.assertEqual(cal.normalize_lt(65535, profile["lt"]), 1)

    def test_inverted_and_centered_trigger_polarities(self):
        # Support inverted and centered trigger-axis polarity from explicit phase evidence.
        # Supply inverted and centered-neutral trigger samples with known pressed endpoints.
        # Normalization must follow observed polarity instead of assuming a zero-based axis.
        for neutral, full in ((65535, 0), (32767, 0), (32767, 65535)):
            with self.subTest(neutral=neutral, full=full):
                profile = cal.infer_calibration(evidence(neutral, full, lt_button=0), DEVICE)
                self.assertEqual(cal.normalize_lt(neutral, profile["lt"]), 0)
                self.assertEqual(cal.normalize_lt(full, profile["lt"]), 1)
                self.assertAlmostEqual(cal.normalize_lt((neutral + full) / 2, profile["lt"]), 0.5)

    def test_xinput_ranges_are_explicit_and_inference_remains_prompt_based(self):
        # Keep XInput ranges explicit without inventing a prompted calibration.
        # Generate XInput phase evidence across its declared axis ranges.
        # Backend metadata must constrain normalization without replacing prompted control identification.
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
        # Reject ambiguous calibration when multiple independent axes change.
        # Make more than one axis track the trigger prompt.
        # Calibration must refuse ambiguous evidence instead of arbitrarily choosing an axis.
        phases = evidence()
        for phase in ("lt", "both"):
            for sample in phases[phase]:
                sample["axes"]["u"] = 65535
        with self.assertRaisesRegex(ValueError, "one clearly changed LT axis"):
            cal.infer_calibration(phases, DEVICE)

    def test_missing_or_partial_trigger_motion_is_rejected(self):
        # Reject missing trigger movement and incomplete travel evidence.
        # Remove trigger travel or provide insufficient separation from neutral.
        # A weak calibration must not turn noise into a gameplay activation.
        for full in (0, 10000, 45000):
            with self.subTest(full=full), self.assertRaises(ValueError):
                cal.infer_calibration(evidence(full=full), DEVICE)

    def test_ambiguous_or_inconsistent_button_masks_are_rejected(self):
        # Reject inconsistent button masks instead of guessing their meaning.
        # Vary modifier bits inconsistently across isolated and combined prompted phases.
        # The saved mapping must represent one reproducible control rather than coincident noise.
        for phase, mask in (("lb", 0x30), ("lt", 0x10), ("lt", 0x60),
                            ("both", 0x10), ("neutral", 1), ("release", 1)):
            phases = evidence()
            for sample in phases[phase]:
                sample["buttons"] = mask
            with self.subTest(phase=phase, mask=mask), self.assertRaises(ValueError):
                cal.infer_calibration(phases, DEVICE)

    def test_release_and_both_phase_axis_validation(self):
        # Validate release and combined-button phases against the same trigger model.
        # Corrupt released or combined-phase trigger evidence while isolated press data remains plausible.
        # Inference must check the whole prompted sequence before accepting a mapping.
        for phase, value in (("release", 20000), ("lb", 20000), ("both", 45000)):
            phases = evidence()
            for sample in phases[phase]:
                sample["axes"]["v"] = value
            with self.subTest(phase=phase), self.assertRaises(ValueError):
                cal.infer_calibration(phases, DEVICE)

    def test_unstable_axis_or_too_few_samples_rejected(self):
        # Reject unstable neutral samples and insufficient calibration evidence.
        # Provide noisy endpoints and insufficient sample counts.
        # One convenient sample cannot establish a reliable controller binding.
        phases = evidence()
        phases["lt"][0]["axes"]["v"] = 30000
        with self.assertRaisesRegex(ValueError, "Unstable"):
            cal.infer_calibration(phases, DEVICE)
        with self.assertRaisesRegex(ValueError, "Too few"):
            cal.infer_calibration(dict(evidence(), lb=[]), DEVICE)

    def test_invalid_axis_cannot_normalize(self):
        # Refuse axis normalization outside the observed device bounds.
        # Pass malformed or out-of-range values through the inferred trigger normalizer.
        # Invalid input must fail closed rather than become an extreme valid press.
        mapping = cal.infer_calibration(evidence(), DEVICE)["lt"]
        for value in (None, True, "0", float("nan"), float("inf"), -1, 65536, 10 ** 1000):
            with self.subTest(value=value):
                self.assertIsNone(cal.normalize_lt(value, mapping))


class AdapterTests(unittest.TestCase):
    def setUp(self):
        # Construct the logical chord adapter from inferred fixture calibration.
        # Reuse the same phase evidence and device capabilities as calibration tests.
        # Input adaptation must consume the persisted mapping rather than a separate hardcoded layout.
        self.adapter = cal.CalibratedChord(cal.infer_calibration(evidence(), DEVICE))

    def device(self, **changes):
        # Send device identity and capability changes to the chord adapter.
        # Keep gameplay context valid while varying only the discovery metadata.
        # Reconnect tests must separate incompatible devices from input-state changes.
        return self.adapter.process(dict(DEVICE, kind="input_device", **changes), context_valid=True)

    def state(self, buttons, axis, unknown=False, context_valid=True):
        # Feed raw button and trigger-axis observations through the calibrated adapter.
        # Choose explicit edge provenance and gameplay-context validity.
        # A held snapshot or invalid context must not manufacture a fresh chord press.
        return self.adapter.process(dict(kind="input", backend="winmm", slot=0,
            observed_monotonic=1.0, buttons=buttons, axes={"v": axis},
            edge_basis="unknown" if unknown else "previous_observation"), context_valid=context_valid)

    def test_initial_held_releases_then_fires_once(self):
        # Require release after initial held input before emitting one chord.
        # Feed a held startup snapshot, neutral state and one fresh chord.
        # The adapter must distinguish attachment state from an intentional rising edge.
        self.device()
        self.assertFalse(self.state(0x50, 65535, unknown=True)["chord_candidate"])
        self.assertFalse(self.state(0, 0)["chord_candidate"])
        self.assertTrue(self.state(0x50, 65535)["chord_candidate"])
        self.assertFalse(self.state(0x50, 65535)["chord_candidate"])

    def test_reconnect_held_requires_compatible_device_and_release(self):
        # Require compatible-device evidence and neutral input after reconnect.
        # Reconnect the same calibrated device with controls still pressed.
        # Compatibility permits reuse of the mapping but cannot authorize a fabricated press.
        self.device()
        self.state(0, 0, unknown=True)
        self.adapter.process(dict(kind="input_unavailable", backend="winmm", slot=0), context_valid=True)
        self.assertFalse(self.state(0x50, 65535)["chord_candidate"])
        self.device()
        self.assertFalse(self.state(0x50, 65535, unknown=True)["chord_candidate"])
        self.state(0, 0)
        self.assertTrue(self.state(0x50, 65535)["chord_candidate"])

    def test_changed_device_capabilities_fail_closed(self):
        # Disarm when a device's declared capabilities change.
        # Alter saved device capabilities after the adapter has seen the original device.
        # An incompatible replacement must not inherit the previous control interpretation.
        event = dict(DEVICE, kind="input_device")
        event["product"] = 99
        self.assertFalse(self.adapter.process(event, context_valid=True)["accepted"])
        self.state(0, 0, unknown=True)
        self.assertFalse(self.state(0x50, 65535)["chord_candidate"])

    def test_unseen_device_and_other_streams_cannot_fire(self):
        # Reject unseen devices and unrelated backend streams.
        # Send input before discovery and from a different backend or slot.
        # Only the identified calibrated stream may produce logical chord events.
        self.state(0, 0, unknown=True)
        self.assertFalse(self.state(0x50, 65535)["chord_candidate"])
        self.device()
        self.state(0, 0, unknown=True)
        self.assertIsNone(self.adapter.process(dict(kind="input", backend="xinput", slot=0,
                         buttons=0x50, axes={"v": 65535}), context_valid=True))

    def test_context_loss_and_invalid_axis_disarm(self):
        # Disarm on context loss or invalid trigger values.
        # Invalidate gameplay context or trigger data during an armed chord.
        # Restoring valid samples must require a new neutral observation before activation.
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
        # Accept calibration cues only when their phase JSON matches exactly.
        # Read missing, malformed and wrong-phase cue files.
        # A stale or vaguely matching acknowledgement must not advance calibration.
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "cue.json"
            self.assertFalse(cal.cue_matches(path, "neutral"))
            for content in ('{', '"neutral"', '{"phase":"NEUTRAL"}', '{"phase":"lb"}', '{"phase":true}'):
                path.write_text(content)
                self.assertFalse(cal.cue_matches(path, "neutral"))
            path.write_text('{"phase":"neutral"}', encoding="utf-8-sig")
            self.assertTrue(cal.cue_matches(path, "neutral"))

    def test_wait_deadline_keeps_polling_and_records_failed_status(self):
        # Keep collecting observations until the bounded prompt deadline expires.
        # Advance a fake clock while no valid cue arrives and log continued reader polls.
        # The timeout must preserve evidence and a failed status without blocking indefinitely.
        for total, wait, reason in ((10, 0.05, "Timed out waiting"), (0.04, 10, "Total calibration deadline")):
            clock = [0.0]
            calls = [0]
            class Reader:
                def poll(self):
                    # Record each poll while a calibration cue never arrives.
                    # Return timestamped fixture events on every simulated poll.
                    # The cue deadline must still retain evidence and avoid a blocking input wait.
                    calls[0] += 1
                    return [dict(kind="fixture_poll", observed_monotonic=clock[0])]
            def sleep(seconds):
                # Advance the cue-wait clock by the requested polling delay.
                # Avoid wall-clock sleeping while retaining deadline arithmetic.
                # A missing calibration cue must terminate in bounded test time.
                clock[0] += seconds
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as td, \
                    patch.object(cal.time, "perf_counter", side_effect=lambda: (
                        # Expose the cue-timeout test's manually advanced clock.
                        # Read the same cell changed by its fake sleep function.
                        # The collector's deadline must expire without wall-clock waiting.
                        clock[0]
                    )), \
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
        # Prevent a stale cue from satisfying a later calibration phase.
        # Leave the neutral cue present when the collector requests the following phase.
        # Each phase requires its own acknowledgement so samples cannot be mislabeled.
        clock = [0.0]
        neutral = evidence()["neutral"][0]
        class Reader:
            first = True
            def poll(self):
                # Emit one device event followed by neutral samples.
                # Keep the same device connected while the previous phase's cue remains stale.
                # The collector must require a new matching cue before entering another phase.
                events = []
                if self.first:
                    events.append(dict(DEVICE, kind="input_device", observed_monotonic=clock[0]))
                    self.first = False
                return events + [dict(neutral, kind="input", backend="winmm", slot=0,
                                      observed_monotonic=clock[0])]
        def sleep(seconds):
            # Advance the stale-cue scenario's simulated clock.
            # Preserve each requested delay so the next-phase deadline expires normally.
            # A stale acknowledgement must not turn a timed wait into a busy loop.
            clock[0] += seconds
        with tempfile.TemporaryDirectory() as td, \
                patch.object(cal.time, "perf_counter", side_effect=lambda: (
                    # Expose time for the stale-previous-cue scenario.
                    # Read the clock advanced between neutral samples.
                    # A missing next-phase cue must reach its own deadline deterministically.
                    clock[0]
                )), \
                patch.object(cal.time, "sleep", side_effect=sleep), patch("builtins.print"), \
                patch.object(cal, "cue_matches", side_effect=lambda path, phase: (
                    # Acknowledge only the neutral phase in the cue fixture.
                    # Reject every subsequent phase despite its repeated polling.
                    # The collector must not reuse a previous phase's successful acknowledgement.
                    phase == "neutral"
                )):
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
        # Abort calibration when the controller disconnects or changes identity.
        # Emit a device loss or replacement during prompted collection.
        # A saved calibration cannot combine raw evidence from different input identities.
        for failure in (dict(kind="input_unavailable", backend="winmm", slot=0),
                        dict(DEVICE, kind="input_device", product=99)):
            class Reader:
                def poll(self):
                    # Report the expected device followed by the selected identity failure.
                    # Replay disconnect and changed-device events through the production collector.
                    # Calibration must stop before mixing samples from different physical input streams.
                    return [dict(DEVICE, kind="input_device"), failure]
            with self.subTest(failure=failure), patch("builtins.print"), self.assertRaises(ValueError):
                cal.collect(Reader(), "winmm", 0, 1, 1, io.StringIO())

    def test_bounded_prompted_phases_preserve_raw_evidence(self):
        # Retain raw evidence from every bounded prompted calibration phase.
        # Drive every prompt with its corresponding raw samples and deterministic elapsed time.
        # The completed mapping must remain auditable from the retained phase evidence.
        phases = evidence()
        clock = [0.0]
        current = ["neutral"]

        class Reader:
            first = True

            def poll(self):
                # Emit the prompted phase's raw fixture sample at the current time.
                # Publish device identity once, then follow the phase selected by the prompt callback.
                # Saved evidence must correspond to the explicit prompt rather than an inferred gesture.
                events = []
                if self.first:
                    events.append(dict(DEVICE, kind="input_device", observed_monotonic=clock[0]))
                    self.first = False
                events.append(dict(phases[current[0]][0], kind="input", backend="winmm",
                                   slot=0, observed_monotonic=clock[0]))
                return events

        def prompt(message, **kwargs):
            # Select the sample phase from the collector's displayed prompt.
            # Parse only its phase prefix and update the reader's current fixture phase.
            # The test follows the real prompt sequence without an interactive console.
            current[0] = message.split(":", 1)[0].lower()

        def sleep(seconds):
            # Advance the successful calibration scenario's clock deterministically.
            # Let each requested sampling interval contribute to its bounded phase duration.
            # Complete raw evidence can be collected without waiting through real prompts.
            clock[0] += seconds

        stream = io.StringIO()
        with patch.object(cal.time, "perf_counter", side_effect=lambda: (
            # Expose the successful prompted collection's simulated clock.
            # Share time with the phase-specific reader and fake delay.
            # Evidence timestamps and collection bounds must remain internally consistent.
            clock[0]
        )), \
                patch.object(cal.time, "sleep", side_effect=sleep), patch("builtins.print", side_effect=prompt):
            profile = cal.collect(Reader(), "winmm", 0, 1, 1, stream)
        rows = [json.loads(line) for line in stream.getvalue().splitlines()]
        self.assertEqual(profile["lb_mask"], 0x10)
        self.assertGreaterEqual(clock[0], 10)
        self.assertLess(clock[0], 10.1)
        self.assertEqual({r["phase"] for r in rows}, {p for p, _ in cal.PHASES})
        self.assertTrue(any(r["kind"] == "calibration_sample" for r in rows))
