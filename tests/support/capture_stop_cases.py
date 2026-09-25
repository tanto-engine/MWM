import contextlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "runtime"))
import boss_probe as probe


PLAYER = 0x90000
BOSS = 0x91000
EXTRA = 0x92000


class FakeClock:
    def __init__(self):
        # Start sampling time at a fixed nonzero monotonic value.
        # Store time locally rather than replacing the recorder's scheduling arithmetic.
        # Duration and interruption tests remain deterministic across machines.
        self.now = 100.0

    def perf_counter(self):
        # Expose the simulated monotonic clock to the capture loop.
        # Return the value advanced by the fake sleep operation.
        # Elapsed-time checks can run at full test speed without changing production code.
        return self.now

    def sleep(self, seconds):
        # A stalled loop should fail quickly rather than hang the test runner.
        # Advance sampling time only when the recorder yields positively.
        # Reject zero or negative delays before updating the simulated clock.
        # A stalled sampler should fail immediately instead of hanging the test runner.
        if seconds <= 0:
            raise AssertionError("Expected the sampler to yield between samples")
        self.now += seconds


class FakeGame:
    def __init__(self, fault=None, fault_address=BOSS, changes=False):
        # Configure a selected actor failure and optional ordinary action changes.
        # Track sample passes and per-actor snapshot counts separately.
        # Tests can place identity loss during initial, verification or metadata reads.
        self.identity = {"pid": 123, "creation_filetime": "fixture"}
        self.sample = 0
        self.fault = fault
        self.fault_address = fault_address
        self.changes = changes
        self.observed = []
        self.snapshot_calls = {}

    def alive(self):
        # Keep the fake process alive throughout actor-replacement scenarios.
        # Return true so only the selected actor's identity can end the take.
        # Process exit must not mask a failure to rediscover retired actor objects.
        return True

    def begin_sample(self):
        # Start a fresh capture pass and clear per-pass read counters.
        # Fail after 100 passes to catch a recorder that ignores its duration.
        # Bounded owned-memory tests must never hang on lifecycle regressions.
        self.sample += 1
        self.snapshot_calls = {}
        if self.sample > 100:
            raise AssertionError("Capture failed to honor its duration")

    def snapshot(self, address):
        # Change one actor's ownership or readability at a selected read phase.
        # Keep other actors valid and optionally alternate only current descriptors.
        # The recorder must separate replacement, read races and normal action transitions.
        self.observed.append((self.sample, address))
        self.snapshot_calls[address] = self.snapshot_calls.get(address, 0) + 1
        call = self.snapshot_calls[address]
        affected = self.sample >= 2 and address == self.fault_address
        unavailable = (self.fault == "unreadable"
                       or self.fault == "verification_unreadable" and call >= 2
                       or self.fault == "metadata_snapshot_unreadable" and call >= 3)
        if affected and unavailable:
            raise OSError("Fixture: object no longer has expected vtable")
        raw = bytearray(0xF0)
        owner = 0x88000 + address - PLAYER
        if affected and (self.fault == "owner" or self.fault == "verification_owner" and call >= 2):
            owner += 0x100000
        current = 0x10000 + (self.sample % 2) * 0x1000 if self.changes else 0x10000
        struct.pack_into("<QQ", raw, 0x50, owner, current)
        struct.pack_into("<I", raw, 0x68, self.sample if self.changes else 1)
        return bytes(raw), probe.object_fields(raw)

    def bytes(self, address, count):
        # Expose only the two descriptor blocks used by action-change scenarios.
        # Vary their low action word while refusing all optional metadata ranges.
        # Missing metadata must not be confused with a lost actor identity.
        if address in (0x10000, 0x11000) and count == 0xD0:
            raw = bytearray(count)
            struct.pack_into("<H", raw, 0, 0xCF0 + (address == 0x11000))
            return bytes(raw)
        raise OSError("Fixture: optional metadata range is unavailable")


class CaptureStopTests(unittest.TestCase):
    def run_capture(self, game, metadata_failure=False, include_extra=False, player=PLAYER, boss=BOSS):
        # Run the real recording loop against fake actors, clock and neutral inputs.
        # Write events to a temporary take and read its final status back.
        # Stop behavior is checked through retained evidence rather than private loop state.
        objects = [PLAYER, BOSS] + ([EXTRA] if include_extra else [])
        cfg = dict(game.identity, candidates=[
            {"object": hex(address), "owner_like": hex(0x88000 + address - PLAYER)}
            for address in objects
        ])
        controller = SimpleNamespace(ControllerReader=lambda: (
            # Create a controller double with no physical input source.
            # Supply only the poll and status interfaces the recorder consumes.
            # Actor-loss tests must not touch device enumeration or calibration.
            SimpleNamespace(
            poll=lambda: (
                # Return no controller events in the actor-lifecycle fixture.
                # Keep gesture activity absent while snapshots change or fail.
                # A recording stop must be attributable to actor identity, not input state.
                []
            ), status=lambda: (
                # Return a serializable empty controller status in the fixture.
                # Avoid claiming a calibrated or connected physical device.
                # Lifecycle evidence must be testable without any real controller.
                {}
            ))
        ))
        clock = FakeClock()
        with tempfile.TemporaryDirectory() as td, contextlib.ExitStack() as stack:
            folder = Path(td) / "capture"
            stack.enter_context(patch.dict(sys.modules, {"controller_reader": controller}))
            stack.enter_context(patch.object(probe.time, "perf_counter", clock.perf_counter))
            stack.enter_context(patch.object(probe.time, "sleep", clock.sleep))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            if metadata_failure:
                stack.enter_context(patch.object(probe, "metadata", side_effect=OSError("fixture metadata failure")))
            probe.record(game, cfg, folder, 0.05, 10, player, boss, 4)
            final = json.loads((folder / "status.json").read_text())
            events = [json.loads(line) for line in (folder / "events.jsonl").read_text().splitlines()]
        self.assertFalse(final["running"])
        self.assertEqual(events[-1]["kind"], "end")
        self.assertEqual(events[-1]["stop_reason"], final["stop_reason"])
        return final, events

    def assert_selected_loss(self, game, **roles):
        # Check that selected identity loss ends capture in its second pass.
        # Inspect the rediscovery marker and exclude trusted events for the replacement.
        # No surviving actor may allow recording to continue under a stale selected role.
        final, events = self.run_capture(game, **roles)
        self.assertEqual(final["stop_reason"], "selected_actor_invalid_rediscovery_required")
        self.assertLess(final["seconds"], 0.05)
        self.assertEqual(game.sample, 2, "Do not keep sampling after a selected actor loses identity")
        stops = [event for event in events if event["kind"] == "rediscovery_required"]
        self.assertEqual(len(stops), 1)
        self.assertEqual(stops[0]["objects"], [hex(game.fault_address)])
        # A replaced actor must never produce a trusted role observation.
        bad = [event for event in events if event["kind"] == "action_state"
               and event["object"] == hex(game.fault_address) and event["t"] >= 0.01]
        self.assertEqual(bad, [])

    def test_selected_boss_loss_stops_even_while_player_remains_valid(self):
        # Rediscover after the selected boss disappears while William remains valid.
        # Retire only the selected boss while William continues to produce valid snapshots.
        # A surviving player must not let the take silently lose its source actor.
        self.assert_selected_loss(FakeGame(fault="unreadable", fault_address=BOSS))

    def test_selected_player_loss_stops_even_while_boss_remains_valid(self):
        # Rediscover after William disappears while the selected boss remains valid.
        # Retire only the selected player and leave the boss readable.
        # A take requiring both identities must rediscover when either one is replaced.
        self.assert_selected_loss(FakeGame(fault="unreadable", fault_address=PLAYER))

    def test_selected_owner_change_stops_without_relabeling_replacement(self):
        # Reject replaced owners without relabeling them as trusted actors.
        # Reuse the selected actor address with a different owner pointer.
        # The replacement must never inherit the old player's or boss's trusted role.
        for address in (PLAYER, BOSS):
            with self.subTest(address=hex(address)):
                self.assert_selected_loss(FakeGame(fault="owner", fault_address=address))

    def test_selected_actor_loss_during_verification_stops_in_same_pass(self):
        # Detect selected-actor loss during the second snapshot of the same sample.
        # Fail the second snapshot that verifies a selected actor's sampled state.
        # The recorder must stop before publishing that torn state as trusted evidence.
        for fault in ("verification_unreadable", "verification_owner"):
            with self.subTest(fault=fault):
                self.assert_selected_loss(FakeGame(fault=fault, changes=True))

    def test_selected_actor_loss_during_metadata_check_stops_in_same_pass(self):
        # Detect selected-actor loss during metadata consistency verification.
        # Retire the actor during the later metadata-consistency snapshot.
        # Identity loss discovered after the initial state read must still end this pass.
        game = FakeGame(fault="metadata_snapshot_unreadable", changes=True)
        final, _ = self.run_capture(game)
        # The action snapshot before the failing metadata check was valid.
        self.assertEqual(final["stop_reason"], "selected_actor_invalid_rediscovery_required")
        self.assertEqual(game.sample, 2)

    def test_duration_stops_with_both_actors_still_valid(self):
        # End a healthy capture only at its requested duration.
        # Keep both identities stable while advancing the fake clock to the take limit.
        # The sampler must honor its duration without relying on a lifecycle failure to exit.
        final, _ = self.run_capture(FakeGame())
        self.assertEqual(final["stop_reason"], "duration")
        self.assertGreaterEqual(final["seconds"], 0.05)
        self.assertLess(final["seconds"], 0.061)

    def test_ordinary_action_changes_do_not_stop_capture(self):
        # Keep recording ordinary action transitions without confusing them with actor replacement.
        # Alternate valid current descriptors while keeping owner and actor identity stable.
        # Routine combat transitions must remain part of one continuous recording take.
        final, events = self.run_capture(FakeGame(changes=True))
        self.assertEqual(final["stop_reason"], "duration")
        for address in (PLAYER, BOSS):
            states = [event for event in events if event["kind"] == "action_state"
                      and event["object"] == hex(address)]
            self.assertGreater(len(states), 2)
            self.assertEqual(len({event["current"] for event in states}), 2)

    def test_optional_metadata_failure_does_not_mean_actor_was_lost(self):
        # Allow optional metadata failure while actor identity remains valid.
        # Fail optional payload expansion while selected actor snapshots remain valid.
        # Missing metadata should preserve the observation without unnecessary rediscovery.
        final, events = self.run_capture(FakeGame(changes=True), metadata_failure=True)
        self.assertEqual(final["stop_reason"], "duration")
        self.assertTrue(any(event["kind"] == "metadata_unreadable" for event in events))

    def test_unselected_object_loss_does_not_stop_selected_actor_capture(self):
        # Ignore an unrelated candidate disappearing during identified-boss capture.
        # Retire an extra discovered candidate outside the selected player/boss pair.
        # Known-boss capture should not restart because an unrelated object disappeared.
        game = FakeGame(fault="unreadable", fault_address=EXTRA)
        final, events = self.run_capture(game, include_extra=True)
        self.assertEqual(final["stop_reason"], "duration")
        self.assertTrue(any(event["kind"] == "object_unreadable"
                            and event["object"] == hex(EXTRA) for event in events))

    def test_scout_candidate_loss_requests_rediscovery_while_other_actors_survive(self):
        # Rediscover lost or replaced scout candidates even when other actors survive.
        # Retire each unassigned candidate during several snapshot phases.
        # Scout mode must treat every candidate identity as required until roles are known.
        for player in (PLAYER, None):
            for address in (BOSS, EXTRA):
                for fault in ("unreadable", "owner"):
                    with self.subTest(player=player, address=address, fault=fault):
                        self.assert_selected_loss(FakeGame(fault=fault, fault_address=address),
                                                  player=player, boss=None, include_extra=True)

    def test_scout_action_changes_preserve_unassigned_roles_without_rediscovery(self):
        # Preserve unassigned scout roles while ordinary actions continue changing.
        # Change only current actions for the unassigned discovered actors.
        # Scout capture must retain unknown roles and continue through ordinary combat.
        game=FakeGame(changes=True)
        final,events=self.run_capture(game,boss=None,include_extra=True)
        self.assertEqual(final["stop_reason"],"duration")
        states=[event for event in events if event["kind"]=="action_state"]
        self.assertTrue(any(event["object"]==hex(BOSS) and event["role"]=="unassigned" for event in states))
        self.assertFalse(any(event["kind"]=="rediscovery_required" for event in events))
