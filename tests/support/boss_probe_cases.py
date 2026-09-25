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
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "runtime"))
import boss_probe as probe


class FakeBytes:
    def __init__(self, pieces):
        # Prepare isolated readable blocks for metadata decoding.
        # Retain the supplied blocks and a log of requested ranges.
        # Tests can prove decoding stays inside the selected transition slice.
        self.pieces = pieces
        self.reads = []

    def bytes(self, address, count):
        # Copy only ranges fully contained in a supplied fixture block.
        # Record each request and raise OSError for unavailable metadata.
        # Optional read failures must remain explicit rather than become fabricated bytes.
        self.reads.append((address, count))
        for base, raw in self.pieces.items():
            if base <= address and address + count <= base + len(raw):
                return bytes(raw[address - base:address - base + count])
        raise OSError("fake unavailable range")


def descriptor(payload=0x20000, table=0x30000, start=2, count=3):
    # Create a native-sized descriptor with a nonzero transition slice start.
    # Encode payload and transition-table pointer plus the 16-bit start/count fields.
    # Offset mistakes must be detectable when the valid rows do not begin at zero.
    raw = bytearray(0xD0)
    struct.pack_into("<H", raw, 0, 0xD4E)
    struct.pack_into("<Q", raw, 0x20, payload)
    struct.pack_into("<QHH", raw, 0x78, table, start, count)
    return raw


class ReadSafetyTests(unittest.TestCase):
    def test_seed_scans_only_nearby_pool_and_rejects_a_previous_process(self):
        # Find a rebuilt actor beside a retired address without scanning unrelated heap regions.
        # Verify the exact read budget and reject a stale process birth before reading memory.
        # Signature selection remains separate from this candidate-discovery optimization.
        raw=bytearray(0x10000); struct.pack_into('<Q',raw,0x200,0x70000)
        identity=dict(pid=10,creation_filetime='100',vtable='0x70000')
        game=SimpleNamespace(pid=10,vtable=0x70000,identity=identity,
            region=Mock(return_value=self.region(0x20000,0x10000)),bytes=Mock(return_value=raw),
            snapshot=Mock(side_effect=[OSError('retired'),(b'',dict(current='0x0',owner_like='0x30000'))]))
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'seed.json'; seed=dict(identity,candidates=[dict(object='0x20010')])
            path.write_text(json.dumps(seed)); result=probe.discover(game,path)
            self.assertEqual(result['bytes_scanned'],0x10000)
            self.assertEqual([item['object'] for item in result['candidates']],['0x20200'])
            game.bytes.assert_called_once_with(0x20000,0x10000)
            game.bytes.reset_mock(); seed['creation_filetime']='old'; path.write_text(json.dumps(seed))
            with self.assertRaisesRegex(ValueError,'identity mismatch'): probe.discover(game,path)
            game.bytes.assert_not_called()

    def game(self, regions):
        # Create a LiveGame instance without opening a process.
        # Replace its region query with the supplied committed/protected memory map.
        # The production range validator can be tested before any Win32 copy occurs.
        game = object.__new__(probe.LiveGame)
        game.handle = 123  # Fake opaque value. Patched read cannot call Win32.

        def region(at):
            # Resolve one address against the supplied fixture memory regions.
            # Raise when the address falls outside every declared region.
            # A cross-region read must inspect all coverage instead of trusting its first page.
            for r in regions:
                if r.BaseAddress <= at < r.BaseAddress + r.RegionSize:
                    return r
            raise OSError("outside fixture")

        game.region = region
        return game

    def region(self, start, size, protect=4, state=0x1000):
        # Represent a VirtualQueryEx region with explicit protection and state.
        # Return the four fields consumed by the production read guard.
        # Tests vary commit and access rights without depending on host memory layout.
        return SimpleNamespace(BaseAddress=start, RegionSize=size, Protect=protect, State=state)

    def test_guard_noaccess_execute_only_and_uncommitted_are_never_read(self):
        # Reject inaccessible regions before any process-memory copy is attempted.
        # Provide guarded, inaccessible, execute-only and uncommitted region descriptions.
        # The reader must reject each range before calling the memory-copy API.
        for protect, state in [(0x104, 0x1000), (1, 0x1000), (0x10, 0x1000), (4, 0x2000)]:
            with self.subTest(protect=protect, state=state):
                game = self.game([self.region(0x10000, 0x1000, protect, state)])
                with patch.object(probe, "read") as read:
                    with self.assertRaises(OSError):
                        game.bytes(0x10000, 8)
                    read.assert_not_called()

    def test_cross_region_read_checks_entire_range_before_read(self):
        # Validate every region crossed by a requested memory span.
        # Span a readable region and an inaccessible neighboring region.
        # Valid first-page protection must not authorize a partially unreadable copy.
        game = self.game([self.region(0x10000, 0x1000), self.region(0x11000, 0x1000, 0x104)])
        with patch.object(probe, "read") as read:
            with self.assertRaises(OSError):
                game.bytes(0x10FF0, 0x20)
            read.assert_not_called()

    def test_invalid_pointer_size_and_overflow_are_never_read(self):
        # Reject pointer overflow, invalid addresses and impossible read sizes.
        # Submit invalid addresses, lengths and wrapped address ranges.
        # Malformed requests must fail before any operating-system read.
        game = self.game([])
        for address, count in [(0, 8), (0x10000, 0), (0x10000, -1),
                               (0x10000, 1024 * 1024 + 1), (probe.MAX_POINTER, 2)]:
            with self.subTest(address=address, count=count), patch.object(probe, "read") as read:
                with self.assertRaises(OSError):
                    game.bytes(address, count)
                read.assert_not_called()

    def test_valid_cross_region_read_is_exact(self):
        # Allow exact reads spanning adjacent readable regions.
        # Cover a requested range with adjacent readable fixture regions.
        # The validator must allow the full range without changing its start or byte count.
        game = self.game([self.region(0x10000, 0x1000), self.region(0x11000, 0x1000, 2)])
        with patch.object(probe, "read", return_value=b"a" * 32) as read:
            self.assertEqual(game.bytes(0x10FF0, 32), b"a" * 32)
            read.assert_called_once_with(123, 0x10FF0, 32)

    def test_reused_object_with_different_vtable_is_rejected(self):
        # Reject an action object whose address has been reused for another type.
        # Return a readable actor block whose vtable no longer matches the supported type.
        # An address remaining mapped does not preserve the original actor's identity.
        game = self.game([])
        game.vtable = 0x70000
        game.bytes = lambda address, count: (
            # Return readable zeroed bytes for the requested fixture range.
            # Match the exact byte count after region validation has succeeded.
            # The range-guard test must inspect copy boundaries without reading a process.
            bytes(count)
        )
        with self.assertRaisesRegex(OSError, "vtable"):
            game.snapshot(0x10000)


class MetadataTests(unittest.TestCase):
    def test_slice_limit_signed_fields_and_flag_widths(self):
        # Preserve transition slice limits and signed native metadata fields.
        # Decode a nonzero transition slice with signed targets and wide native flags.
        # Metadata evidence must preserve widths and stop at the requested row limit.
        payload = bytearray(0x40)
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

    def test_contact_rows_and_native_recovery_are_captured_once_with_bounds(self):
        # Retain native cancel and Pulse fields alongside a bounded source combat slice.
        # Use a nonzero slice start and more rows than the recorder permits in one descriptor.
        # Unknown contact bytes must survive while omitted rows remain explicitly counted.
        raw=descriptor(count=0); payload=bytearray(0x40); contact=bytearray(range(128))
        struct.pack_into('<QHH',raw,0x48,0x30000,2,20)
        struct.pack_into('<hh',payload,0x24,-1,60); payload[0x33]=40
        struct.pack_into('<hhh',payload,0x38,60,25,24)
        contact[0x17]=12; contact[0x1B]=0xF4
        game=FakeBytes({0x10000:raw,0x20000:payload,
                        0x30000:struct.pack('<22Q',0,0,*([0x40000]*20)),0x40000:contact})
        result=probe.metadata(game,0x10000,128)
        self.assertEqual(len(result['combat_entries']),16)
        self.assertEqual(result['combat_entries_omitted'],4)
        self.assertEqual(result['combat_entries'][0]['bytes'],contact.hex())
        self.assertIn((0x30010,16*8),game.reads)
        self.assertEqual(result['payload_prefix']['cancel_frame'],60)
        self.assertEqual(result['payload_prefix']['ki_pulse_start'],60)
        self.assertEqual(result['payload_prefix']['ki_pulse_fill'],25)
        self.assertEqual(result['payload_prefix']['ki_pulse_hold'],24)

    def test_one_retired_combat_row_does_not_discard_other_metadata(self):
        # Isolate a retired contact allocation from valid neighboring source rows.
        # Leave one pointer unreadable while retaining the descriptor, payload and next row.
        # Recovery can catalogue the surviving evidence without inventing the missing contact.
        raw=descriptor(count=0); struct.pack_into('<QHH',raw,0x48,0x30000,0,2)
        game=FakeBytes({0x10000:raw,0x20000:bytes(0x40),
                        0x30000:struct.pack('<2Q',0x40000,0x50000),0x50000:bytes(128)})
        result=probe.metadata(game,0x10000,128)
        self.assertIn('error',result['combat_entries'][0])
        self.assertEqual(result['combat_entries'][1]['bytes'],bytes(128).hex())
        self.assertIn('payload_prefix',result)

    def test_unavailable_payload_and_table_are_explicit(self):
        # Report unavailable payloads and transition tables explicitly.
        # Make optional descriptor payload and transition-table ranges unreadable.
        # The report must retain their failure instead of silently presenting empty trusted metadata.
        game = FakeBytes({0x10000: descriptor()})
        result = probe.metadata(game, 0x10000, 1)
        self.assertIn("payload_error", result)
        self.assertIn("slice_error", result)
        self.assertEqual(result["transition_entries"], [])


class SampleRegionCacheTests(unittest.TestCase):
    def game(self):
        # Construct a handle-free LiveGame with an empty sample-region cache.
        # Bypass initialization and set only the fake handle and cache fields.
        # Cache lifetime checks must not attach to the real game process.
        game = object.__new__(probe.LiveGame)
        game.handle = 123
        game._sample_regions = None
        return game

    @staticmethod
    def query(protect=4):
        # Build a VirtualQueryEx double with configurable page protection.
        # Return a callback that fills the caller-owned region structure.
        # Tests can change protection between sample passes while keeping addresses stable.
        def fill(handle, address, pointer, size):
            # Populate the region structure supplied by the production query call.
            # Write one committed 64-KiB region with the selected protection.
            # The cache test needs real structure mutation rather than a canned Python result.
            mbi = pointer._obj
            mbi.BaseAddress = 0x10000
            mbi.RegionSize = 0x10000
            mbi.State = 0x1000
            mbi.Protect = protect
            return size
        return fill

    def test_same_pass_reuses_region_but_copies_every_range(self):
        # Reuse region metadata within one sample without reusing copied bytes.
        # Read two ranges within one sample and count region queries versus byte copies.
        # Protection caching may reduce queries but must never cache changing action bytes.
        game = self.game()
        with patch.object(probe.kernel, "VirtualQueryEx", side_effect=self.query()) as query, \
                patch.object(probe, "read", return_value=b"a" * 8) as read:
            game.begin_sample()
            game.bytes(0x10000, 8)
            game.bytes(0x19000, 8)
            self.assertEqual(query.call_count, 1)
            self.assertEqual(read.call_count, 2)

    def test_next_pass_requeries_and_rejects_new_guard_before_copy(self):
        # Re-query protection at the next sample before copying a newly guarded page.
        # Change the fixture page to guarded before starting the next sample.
        # A prior readable region must not authorize a later read after lifecycle changes.
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
        # Discard cached region permissions immediately after a failed copy.
        # Fail a copy after a successful region query and retry within the sample.
        # The next attempt must recheck protection rather than reuse stale region evidence.
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
        # Reject recycled process IDs before creating capture output.
        # Pair a saved process id with a different creation identity.
        # Capture must reject it before creating output or opening controller resources.
        game = SimpleNamespace(identity={"pid": 123, "creation_filetime": "new"})
        cfg = {"pid": 123, "creation_filetime": "old", "candidates": [{"object": "0x10000"}]}
        # Import is stubbed as well: no real controller calls from this test.
        controller = SimpleNamespace(ControllerReader=lambda: (
            # Fail if capture constructs a controller after detecting a recycled PID.
            # Raise the test assertion directly from the replacement reader factory.
            # Process identity rejection must precede unrelated device setup.
            self.fail("must reject before controller creation")
        ))
        with tempfile.TemporaryDirectory() as td, patch.dict(sys.modules, {"controller_reader": controller}):
            target = Path(td) / "capture"
            with self.assertRaisesRegex(ValueError, "creation_filetime"):
                probe.record(game, cfg, target, 1, 10, None, None, 0)
            self.assertFalse(target.exists())

    def test_seed_rejects_recycled_pid_before_revalidating_addresses(self):
        # Reject stale discovery seeds before dereferencing their actor addresses.
        # Supply a discovery seed from an earlier process birth.
        # Saved addresses cannot become candidates merely because the numeric PID repeats.
        game = SimpleNamespace(pid=123, vtable=0x70000,
                               identity={"pid": 123, "vtable": "0x70000", "creation_filetime": "new"})
        with tempfile.TemporaryDirectory() as td:
            seed = Path(td) / "seed.json"
            seed.write_text(json.dumps(dict(game.identity, creation_filetime="old", candidates=[])))
            with self.assertRaisesRegex(ValueError, "identity"):
                probe.discover(game, seed)


class CaptureTests(unittest.TestCase):
    def test_shared_descriptor_keeps_selected_boss_expanded_metadata(self):
        # Retain expanded boss metadata when player and boss share a descriptor.
        # Make the player and selected boss observe the same descriptor pointer.
        # Metadata deduplication must not discard the boss's expanded source record.
        game = FakeBytes({0x10000: descriptor(start=0, count=1), 0x20000: bytes(0x38),
                          0x30000: struct.pack("<Q", 0x40000), 0x40000: bytes(0x30)})
        game.identity = {"pid": 123, "creation_filetime": "fake"}
        live = iter([True, False])
        game.alive = lambda: (
            # Expose the fixture's predetermined process-liveness sequence.
            # Consume the next state each time the recorder polls alive.
            # The shared-descriptor scenario must end without a real process or timer.
            next(live)
        )
        raw = bytearray(0xF0)
        struct.pack_into("<Q", raw, 0x50, 0x88000)
        struct.pack_into("<Q", raw, 0x58, 0x10000)
        state = probe.object_fields(raw)
        game.snapshot = lambda address: (
            # Return a copy of the fixture actor snapshot on each read.
            # Keep raw bytes and interpreted fields aligned for consistency checks.
            # Player and boss metadata deduplication must be tested with stable identities.
            (bytes(raw), state.copy())
        )
        objects = [0x90000, 0x91000]
        cfg = dict(game.identity, candidates=[dict(object=hex(a), owner_like=state["owner_like"]) for a in objects])
        controller = SimpleNamespace(ControllerReader=lambda: (
            # Construct a neutral controller double for metadata capture.
            # Expose only poll and status callbacks used by the recorder.
            # The test must not enumerate real devices while inspecting source descriptors.
            SimpleNamespace(poll=lambda: (
            # Produce no controller events during the metadata capture.
            # Return an empty poll result without synthesizing a neutral edge.
            # Metadata retention must remain independent of input activity.
            []
        ), status=lambda: (
            # Expose an empty controller status report for the fake reader.
            # Keep capture-session metadata serializable without hardware fields.
            # The source-descriptor test must not depend on a connected controller.
            {}
        ))
        ))
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
        # Break temporal input associations across missing player observations.
        # Place input events around a gap between otherwise matching player observations.
        # Reports must not associate input with actions that were never continuously observed.
        obj = "0x90000"
        def action(t, current, word):
            # Create a player action observation at a chosen input-association time.
            # Preserve actor and owner while varying descriptor pointer and low action word.
            # Gap handling must be tested independently of actor replacement.
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
