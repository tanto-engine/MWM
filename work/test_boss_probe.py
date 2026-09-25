"""Offline regressions: no process enumeration, attachment, or game reads."""
import contextlib
import csv
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


class FakeBytes:
    def __init__(self, pieces):
        self.pieces = pieces
        self.reads = []

    def bytes(self, address, count):
        self.reads.append((address, count))
        for base, raw in self.pieces.items():
            if base <= address and address + count <= base + len(raw):
                return bytes(raw[address - base:address - base + count])
        raise OSError("fake unavailable range")


def descriptor(payload=0x20000, table=0x30000, start=2, count=3):
    raw = bytearray(0xD0)
    struct.pack_into("<H", raw, 0, 0xD4E)
    struct.pack_into("<Q", raw, 0x20, payload)
    struct.pack_into("<QHH", raw, 0x78, table, start, count)
    return raw


class ReadSafetyTests(unittest.TestCase):
    def game(self, regions):
        game = object.__new__(probe.LiveGame)
        game.handle = 123  # Fake opaque value. Patched read cannot call Win32.

        def region(at):
            for r in regions:
                if r.BaseAddress <= at < r.BaseAddress + r.RegionSize:
                    return r
            raise OSError("outside fixture")

        game.region = region
        return game

    def region(self, start, size, protect=4, state=0x1000):
        return SimpleNamespace(BaseAddress=start, RegionSize=size, Protect=protect, State=state)

    def test_guard_noaccess_execute_only_and_uncommitted_are_never_read(self):
        for protect, state in [(0x104, 0x1000), (1, 0x1000), (0x10, 0x1000), (4, 0x2000)]:
            with self.subTest(protect=protect, state=state):
                game = self.game([self.region(0x10000, 0x1000, protect, state)])
                with patch.object(probe, "read") as read:
                    with self.assertRaises(OSError):
                        game.bytes(0x10000, 8)
                    read.assert_not_called()

    def test_cross_region_read_checks_entire_range_before_read(self):
        game = self.game([self.region(0x10000, 0x1000), self.region(0x11000, 0x1000, 0x104)])
        with patch.object(probe, "read") as read:
            with self.assertRaises(OSError):
                game.bytes(0x10FF0, 0x20)
            read.assert_not_called()

    def test_invalid_pointer_size_and_overflow_are_never_read(self):
        game = self.game([])
        for address, count in [(0, 8), (0x10000, 0), (0x10000, -1),
                               (0x10000, 1024 * 1024 + 1), (probe.MAX_POINTER, 2)]:
            with self.subTest(address=address, count=count), patch.object(probe, "read") as read:
                with self.assertRaises(OSError):
                    game.bytes(address, count)
                read.assert_not_called()

    def test_valid_cross_region_read_is_exact(self):
        game = self.game([self.region(0x10000, 0x1000), self.region(0x11000, 0x1000, 2)])
        with patch.object(probe, "read", return_value=b"a" * 32) as read:
            self.assertEqual(game.bytes(0x10FF0, 32), b"a" * 32)
            read.assert_called_once_with(123, 0x10FF0, 32)

    def test_reused_object_with_different_vtable_is_rejected(self):
        game = self.game([])
        game.vtable = 0x70000
        game.bytes = lambda address, count: bytes(count)
        with self.assertRaisesRegex(OSError, "vtable"):
            game.snapshot(0x10000)


class MetadataTests(unittest.TestCase):
    def test_slice_limit_signed_fields_and_flag_widths(self):
        payload = bytearray(0x38)
        struct.pack_into("<h", payload, 0x0C, -2)
        struct.pack_into("<Q", payload, 0x18, (1 << 34) | (1 << 35))
        struct.pack_into("<i", payload, 0x20, -1)
        struct.pack_into("<h", payload, 0x30, -3)
        entry = bytearray(0x30)
        struct.pack_into("<h", entry, 0x14, -1)
        struct.pack_into("<i", entry, 0x2C, -2)
        game = FakeBytes({0x10000: descriptor(), 0x20000: payload,
                          0x30000: struct.pack("<5Q", 0, 0, 0x40000, 0x50000, 0x60000),
                          0x40000: entry, 0x50000: entry, 0x60000: entry})
        result = probe.metadata(game, 0x10000, 2)
        self.assertEqual(result["entries_omitted"], 1)
        self.assertEqual(len(result["transition_entries"]), 2)
        self.assertNotIn((0x60000, 0x30), game.reads)
        self.assertEqual(result["transition_entries"][0]["target_key_0x14_i16"], -1)
        self.assertEqual(result["transition_entries"][0]["condition_0x2c_i32"], -2)
        self.assertTrue(result["payload_prefix"]["flag_bit34"])
        self.assertTrue(result["payload_prefix"]["flag_bit35"])
        self.assertEqual(result["payload_prefix"]["related_key_0x30_i16"], -3)

    def test_unavailable_payload_and_table_are_explicit(self):
        game = FakeBytes({0x10000: descriptor()})
        result = probe.metadata(game, 0x10000, 1)
        self.assertIn("payload_error", result)
        self.assertIn("slice_error", result)
        self.assertEqual(result["transition_entries"], [])


class SampleRegionCacheTests(unittest.TestCase):
    def game(self):
        game = object.__new__(probe.LiveGame)
        game.handle = 123
        game._sample_regions = None
        return game

    @staticmethod
    def query(protect=4):
        def fill(handle, address, pointer, size):
            mbi = pointer._obj
            mbi.BaseAddress = 0x10000
            mbi.RegionSize = 0x10000
            mbi.State = 0x1000
            mbi.Protect = protect
            return size
        return fill

    def test_same_pass_reuses_region_but_copies_every_range(self):
        game = self.game()
        with patch.object(probe.kernel, "VirtualQueryEx", side_effect=self.query()) as query, \
                patch.object(probe, "read", return_value=b"a" * 8) as read:
            game.begin_sample()
            game.bytes(0x10000, 8)
            game.bytes(0x19000, 8)
            self.assertEqual(query.call_count, 1)
            self.assertEqual(read.call_count, 2)

    def test_next_pass_requeries_and_rejects_new_guard_before_copy(self):
        game = self.game()
        with patch.object(probe.kernel, "VirtualQueryEx", side_effect=self.query()) as query, \
                patch.object(probe, "read", return_value=b"a" * 8) as read:
            game.begin_sample()
            game.bytes(0x10000, 8)
            game.begin_sample()
            query.side_effect = self.query(0x104)
            with self.assertRaises(OSError):
                game.bytes(0x19000, 8)
            self.assertEqual(query.call_count, 2)
            self.assertEqual(read.call_count, 1)

    def test_failed_copy_invalidates_cache_before_next_read(self):
        game = self.game()
        with patch.object(probe.kernel, "VirtualQueryEx", side_effect=self.query()) as query, \
                patch.object(probe, "read", side_effect=[b"a" * 8, OSError("partial copy"), b"b" * 8]) as read:
            game.begin_sample()
            game.bytes(0x10000, 8)
            with self.assertRaises(OSError):
                game.bytes(0x19000, 8)
            self.assertEqual(game._sample_regions, [])
            self.assertEqual(game.bytes(0x1A000, 8), b"b" * 8)
            self.assertEqual(query.call_count, 2)
            self.assertEqual(read.call_count, 3)


class ProcessIdentityTests(unittest.TestCase):
    def test_record_rejects_recycled_pid_before_creating_output(self):
        game = SimpleNamespace(identity={"pid": 123, "creation_filetime": "new"})
        cfg = {"pid": 123, "creation_filetime": "old", "candidates": [{"object": "0x10000"}]}
        # Import is stubbed as well: no real controller calls from this test.
        controller = SimpleNamespace(ControllerReader=lambda: self.fail("must reject before controller creation"))
        with tempfile.TemporaryDirectory() as td, patch.dict(sys.modules, {"controller_reader": controller}):
            target = Path(td) / "capture"
            with self.assertRaisesRegex(ValueError, "creation_filetime"):
                probe.record(game, cfg, target, 1, 10, None, None, 0)
            self.assertFalse(target.exists())

    def test_seed_rejects_recycled_pid_before_revalidating_addresses(self):
        game = SimpleNamespace(pid=123, vtable=0x70000,
                               identity={"pid": 123, "vtable": "0x70000", "creation_filetime": "new"})
        with tempfile.TemporaryDirectory() as td:
            seed = Path(td) / "seed.json"
            seed.write_text(json.dumps(dict(game.identity, creation_filetime="old", candidates=[])))
            with self.assertRaisesRegex(ValueError, "identity"):
                probe.discover(game, seed)


class CaptureTests(unittest.TestCase):
    def test_shared_descriptor_keeps_selected_boss_expanded_metadata(self):
        game = FakeBytes({0x10000: descriptor(start=0, count=1), 0x20000: bytes(0x38),
                          0x30000: struct.pack("<Q", 0x40000), 0x40000: bytes(0x30)})
        game.identity = {"pid": 123, "creation_filetime": "fake"}
        live = iter([True, False])
        game.alive = lambda: next(live)
        raw = bytearray(0xF0)
        struct.pack_into("<Q", raw, 0x50, 0x88000)
        struct.pack_into("<Q", raw, 0x58, 0x10000)
        state = probe.object_fields(raw)
        game.snapshot = lambda address: (bytes(raw), state.copy())
        objects = [0x90000, 0x91000]
        cfg = dict(game.identity, candidates=[dict(object=hex(a), owner_like=state["owner_like"]) for a in objects])
        controller = SimpleNamespace(ControllerReader=lambda: SimpleNamespace(poll=lambda: [], status=lambda: {}))
        with tempfile.TemporaryDirectory() as td, patch.dict(sys.modules, {"controller_reader": controller}):
            folder = Path(td) / "capture"
            with contextlib.redirect_stdout(io.StringIO()):
                probe.record(game, cfg, folder, 1, 5, None, objects[1], 1)
            events = [json.loads(s) for s in (folder / "events.jsonl").read_text().splitlines()]
            metadata = [e for e in events if e["kind"] == "metadata"]
            self.assertEqual(len(metadata), 2)
            boss = next(e for e in metadata if e["role"] == "boss_candidate")
            self.assertEqual(len(boss["transition_entries"]), 1)


class ReportTests(unittest.TestCase):
    def test_input_associations_do_not_bridge_player_observation_gaps(self):
        obj = "0x90000"
        def action(t, current, word):
            return dict(kind="action_state", t=t, object=obj, role="player_candidate",
                        owner_like="0x88000", current=current, index=1,
                        descriptor={"word0_hex": word})
        events = [dict(kind="session", t=0, player_candidate=obj),
                  action(0.1, "0x10000", "0x0CF0"),
                  dict(kind="object_unreadable", t=0.2, object=obj),
                  dict(kind="input", t=0.3, backend="fake", slot=0, buttons=1, pressed_mask=1, released_mask=0),
                  dict(kind="snapshot_race", t=0.4, object=obj),
                  action(0.5, "0x11000", "0x0CF1")]
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "events.jsonl"
            source.write_text("\n".join(json.dumps(e) for e in events))
            output = Path(td) / "report"
            with contextlib.redirect_stdout(io.StringIO()):
                probe.report(source, output)
            with (output / "input_action_links.csv").open(encoding="utf-8-sig", newline="") as f:
                links = list(csv.DictReader(f))
            self.assertEqual(len(links), 1)
            self.assertEqual(links[0]["last_player_word0"], "")
            self.assertEqual(links[0]["next_player_word0"], "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
