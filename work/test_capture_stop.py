"""Offline capture-boundary tests. No process or controller is opened."""
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "outputs" / "boss-probe"))
import boss_probe as probe


PLAYER = 0x90000
BOSS = 0x91000
EXTRA = 0x92000


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def perf_counter(self):
        return self.now

    def sleep(self, seconds):
        # A stalled loop should fail quickly rather than hang the test runner.
        if seconds <= 0:
            raise AssertionError("Expected the sampler to yield between samples")
        self.now += seconds


class FakeGame:
    def __init__(self, fault=None, fault_address=BOSS, changes=False):
        self.identity = {"pid": 123, "creation_filetime": "fixture"}
        self.sample = 0
        self.fault = fault
        self.fault_address = fault_address
        self.changes = changes
        self.observed = []
        self.snapshot_calls = {}

    def alive(self):
        return True

    def begin_sample(self):
        self.sample += 1
        self.snapshot_calls = {}
        if self.sample > 100:
            raise AssertionError("Capture failed to honor its duration")

    def snapshot(self, address):
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
        if address in (0x10000, 0x11000) and count == 0xD0:
            raw = bytearray(count)
            struct.pack_into("<H", raw, 0, 0xCF0 + (address == 0x11000))
            return bytes(raw)
        raise OSError("Fixture: optional metadata range is unavailable")


class CaptureStopTests(unittest.TestCase):
    def run_capture(self, game, metadata_failure=False, include_extra=False):
        objects = [PLAYER, BOSS] + ([EXTRA] if include_extra else [])
        cfg = dict(game.identity, candidates=[
            {"object": hex(address), "owner_like": hex(0x88000 + address - PLAYER)}
            for address in objects
        ])
        controller = SimpleNamespace(ControllerReader=lambda: SimpleNamespace(
            poll=lambda: [], status=lambda: {}))
        clock = FakeClock()
        with tempfile.TemporaryDirectory() as td, contextlib.ExitStack() as stack:
            folder = Path(td) / "capture"
            stack.enter_context(patch.dict(sys.modules, {"controller_reader": controller}))
            stack.enter_context(patch.object(probe.time, "perf_counter", clock.perf_counter))
            stack.enter_context(patch.object(probe.time, "sleep", clock.sleep))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            if metadata_failure:
                stack.enter_context(patch.object(probe, "metadata", side_effect=OSError("fixture metadata failure")))
            probe.record(game, cfg, folder, 0.05, 10, PLAYER, BOSS, 4)
            final = json.loads((folder / "status.json").read_text())
            events = [json.loads(line) for line in (folder / "events.jsonl").read_text().splitlines()]
        self.assertFalse(final["running"])
        self.assertEqual(events[-1]["kind"], "end")
        self.assertEqual(events[-1]["stop_reason"], final["stop_reason"])
        return final, events

    def assert_selected_loss(self, game):
        final, events = self.run_capture(game)
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
        self.assert_selected_loss(FakeGame(fault="unreadable", fault_address=BOSS))

    def test_selected_player_loss_stops_even_while_boss_remains_valid(self):
        self.assert_selected_loss(FakeGame(fault="unreadable", fault_address=PLAYER))

    def test_selected_owner_change_stops_without_relabeling_replacement(self):
        for address in (PLAYER, BOSS):
            with self.subTest(address=hex(address)):
                self.assert_selected_loss(FakeGame(fault="owner", fault_address=address))

    def test_selected_actor_loss_during_verification_stops_in_same_pass(self):
        for fault in ("verification_unreadable", "verification_owner"):
            with self.subTest(fault=fault):
                self.assert_selected_loss(FakeGame(fault=fault, changes=True))

    def test_selected_actor_loss_during_metadata_check_stops_in_same_pass(self):
        game = FakeGame(fault="metadata_snapshot_unreadable", changes=True)
        final, _ = self.run_capture(game)
        # The action snapshot before the failing metadata check was valid.
        self.assertEqual(final["stop_reason"], "selected_actor_invalid_rediscovery_required")
        self.assertEqual(game.sample, 2)

    def test_duration_stops_with_both_actors_still_valid(self):
        final, _ = self.run_capture(FakeGame())
        self.assertEqual(final["stop_reason"], "duration")
        self.assertGreaterEqual(final["seconds"], 0.05)
        self.assertLess(final["seconds"], 0.061)

    def test_ordinary_action_changes_do_not_stop_capture(self):
        final, events = self.run_capture(FakeGame(changes=True))
        self.assertEqual(final["stop_reason"], "duration")
        for address in (PLAYER, BOSS):
            states = [event for event in events if event["kind"] == "action_state"
                      and event["object"] == hex(address)]
            self.assertGreater(len(states), 2)
            self.assertEqual(len({event["current"] for event in states}), 2)

    def test_optional_metadata_failure_does_not_mean_actor_was_lost(self):
        final, events = self.run_capture(FakeGame(changes=True), metadata_failure=True)
        self.assertEqual(final["stop_reason"], "duration")
        self.assertTrue(any(event["kind"] == "metadata_unreadable" for event in events))

    def test_unselected_object_loss_does_not_stop_selected_actor_capture(self):
        game = FakeGame(fault="unreadable", fault_address=EXTRA)
        final, events = self.run_capture(game, include_extra=True)
        self.assertEqual(final["stop_reason"], "duration")
        self.assertTrue(any(event["kind"] == "object_unreadable"
                            and event["object"] == hex(EXTRA) for event in events))


if __name__ == "__main__":
    unittest.main(verbosity=2)
