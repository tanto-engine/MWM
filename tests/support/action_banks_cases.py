# Offline regression cases for bank-scoped native action lookup and invalid record rejection.
# Fixtures isolate game/process effects; these checks do not establish gameplay acceptance.
# Loaded by the existing Engine test entrypoints through Test-Offline.ps1; see CODE_GUIDE.md.
from pathlib import Path
import struct
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "runtime"))
import action_banks as banks


def entry(key, pointer=0x30000, enabled=1, position=0):
    # Describe one native bank entry with a full DWORD key.
    # Allow slot order, enable byte and descriptor identity to vary independently.
    # Lookup precedence tests need collisions without borrowing live actor memory.
    return dict(key_u32=key, key_hex=f"0x{key:08X}", descriptor=hex(pointer),
                enabled_byte=enabled, payload="0x50000", position=position)


def actor(*records):
    # Assemble the ordered bank contexts that native lookup traverses.
    # Assign distinct fixture addresses while keeping each supplied record list intact.
    # Tests must distinguish bank precedence from descriptor-array precedence.
    return {"banks": [{"index": i, "address": hex(0x20000 + i * 0x1000), "records": rows}
                      for i, rows in enumerate(records)]}


def metadata(key=0xC64, enabled=1, payload=0x50000, targets=()):
    # Encode a descriptor and transition targets in the captured metadata shape.
    # Write key, payload and enable byte at native offsets 0, 0x20 and 0x40.
    # The resolver must revalidate source bytes instead of trusting catalogue labels.
    raw = bytearray(0xD0)
    struct.pack_into("<I", raw, 0, key)
    struct.pack_into("<Q", raw, 0x20, payload)
    raw[0x40] = enabled
    return {"descriptor_bytes": raw.hex(),
            "transition_entries": [{"target_key_0x14_i16": target} for target in targets]}


class FakeGame:
    def __init__(self, change=None):
        # Allocate a two-slot bank whose first descriptor pointer is null.
        # Store the array pointer and count together at native bank offset 0x128.
        # Header mutations can then expose torn inspection without a live process.
        self.change = change
        self.snapshots = 0
        self.identity = {"pid": 123}
        header = bytearray(0x138)
        struct.pack_into("<QI", header, 0x128, 0x21000, 2)
        self.pieces = {0x20000: header, 0x21000: struct.pack("<QQ", 0, 0x30000),
                       0x30000: bytes.fromhex(metadata()["descriptor_bytes"])}

    def snapshot(self, address):
        # Return an actor snapshot before or after a controlled identity change.
        # Mutate owner or bank context only after the first snapshot.
        # Inspection must reject replacement while allowing ordinary current-action changes.
        self.snapshots += 1
        raw = bytearray(0xF0)
        struct.pack_into("<Q", raw, 0x70, 0x20000)
        owner = "0x80000"
        if self.snapshots > 1:
            if self.change == "context":
                struct.pack_into("<Q", raw, 0x78, 0x40000)
            if self.change == "owner":
                owner = "0x81000"
        return bytes(raw), {"owner_like": owner, "current": hex(self.snapshots * 0x10000)}

    def bytes(self, address, count):
        # Serve bounded reads from the fixture's bank and descriptor blocks.
        # Optionally change only the repeated bank header read.
        # Any unexpected address fails immediately instead of fabricating readable memory.
        for base, raw in self.pieces.items():
            if base <= address and address + count <= base + len(raw):
                result = bytes(raw[address - base:address - base + count])
                if address == 0x20128 and self.change == "header":
                    result = struct.pack("<QI", 0x21000, 3)
                return result
        raise AssertionError(f"Unexpected fixture read: {address:#x}/{count}")


class NativeLookupTests(unittest.TestCase):
    def test_full_dword_key_is_not_truncated_to_sixteen_bits(self):
        # Keep full DWORD action identities distinct from their low-word aliases.
        # Place keys with the same low word in one native-bank fixture.
        # The 32-bit source identity must select only its exact descriptor.
        source = actor([entry(0x12340C64, 0x30000), entry(0xC64, 0x40000)])
        self.assertEqual(banks.resolve(source, 0xC64)["descriptor"], "0x40000")
        self.assertEqual(banks.resolve(source, 0x12340C64)["descriptor"], "0x30000")

    def test_first_enabled_match_wins_in_bank_then_array_order(self):
        # Match the first enabled descriptor in native bank and array priority.
        # Arrange duplicate keys across ordered banks and descriptor positions.
        # Lookup must match the native first-enabled precedence before importing a payload.
        source = actor([entry(7, 0x30000), entry(7, 0x31000, position=1)],
                       [entry(7, 0x40000)], [entry(7, 0x50000)])
        result = banks.resolve(source, 7)
        self.assertEqual((result["bank_index"], result["descriptor"]), (0, "0x30000"))

    def test_zero_disabled_is_skipped_and_nonzero_is_enabled(self):
        # Respect the native enabled byte without treating every nonzero value as invalid.
        # Vary the descriptor's enable byte across zero and nonzero values.
        # Treating the flag as exactly one would reject valid native records.
        source = actor([entry(7, enabled=0)], [entry(7, 0x40000, enabled=255)])
        result = banks.resolve(source, 7)
        self.assertEqual((result["bank_index"], result["enabled_byte"]), (1, 255))

    def test_all_disabled_or_absent_does_not_resolve(self):
        # Reject absent actions and banks containing only disabled matches.
        # Search banks containing disabled collisions and unrelated keys.
        # A missing enabled source must stay unresolved rather than borrowing another action.
        self.assertIsNone(banks.resolve(actor([], [entry(7, enabled=0)], []), 7))

    def test_out_of_dword_range_is_rejected(self):
        # Reject action keys outside the native DWORD range.
        # Pass negative and overflowing action identities into native lookup.
        # Truncation must not turn malformed catalogue input into a different valid move.
        for key in (-1, 0x100000000):
            with self.subTest(key=key), self.assertRaises(ValueError):
                banks.resolve(actor([]), key)

    def test_inspection_skips_null_slots_and_preserves_positions(self):
        # Preserve null bank positions while inspecting later valid banks.
        # Inspect an owned bank with a null pointer before its valid descriptor.
        # Skipping absent entries must retain the original slot index for evidence.
        result = banks.inspect_banks(FakeGame(), 0x10000)
        self.assertEqual([bank["index"] for bank in result["banks"]], [0, 1, 2])
        self.assertEqual(result["banks"][0]["records"][0]["position"], 1)
        self.assertEqual(result["banks"][0]["records"][0]["key_u32"], 0xC64)
        self.assertIn("not an atomic snapshot", result["consistency"])

    def test_inspection_rejects_header_context_or_owner_changes(self):
        # Reject discovery whose bank headers, context or owner change mid-read.
        # Mutate the header, actor banks or owner between stable-read checks.
        # Preparation must refuse a torn bank view even when individual reads succeed.
        for change in ("header", "context", "owner"):
            with self.subTest(change=change), self.assertRaises(ValueError):
                banks.inspect_banks(FakeGame(change), 0x10000)

    def test_signed_transition_keys_are_sign_extended_and_minus_one_rejected(self):
        # Apply signed transition-key semantics before resolving their target actions.
        # Decode 16-bit transition targets including negative keys and the -1 sentinel.
        # Native sign extension must not invent a descriptor for the no-target marker.
        source = actor([entry(0xC64), entry(0xFFFFFFFF, 0x31000),
                        entry(0xFFFFFFFE, 0x32000), entry(0xFFFF8000, 0x33000)])
        destination = actor([entry(0xFFFE, 0x40000), entry(0x8000, 0x41000)])
        detail = metadata(targets=(-1, -2, -32768, -2))
        with patch.object(banks, "inspect_banks", side_effect=[source, destination]), \
                patch.object(banks, "metadata", return_value=detail):
            result = banks.inspect_pair(SimpleNamespace(identity={}), 1, 2, 0xC64)
        rows = result["direct_transition_comparisons"]
        self.assertEqual([row["transition_key_i16"] for row in rows], [-32768, -2])
        self.assertEqual([row["source"]["key_u32"] for row in rows], [0xFFFF8000, 0xFFFFFFFE])
        self.assertTrue(all(row["destination"] is None for row in rows))

    def test_selected_record_key_enabled_and_payload_are_revalidated(self):
        # Recheck the chosen descriptor identity, enabled byte and payload before use.
        # Alter each decisive descriptor field after selecting its bank entry.
        # A stale lookup result must not authorize a changed or disabled payload.
        for detail in (metadata(key=0xC65), metadata(enabled=0), metadata(payload=0x51000)):
            with self.subTest(detail=detail), \
                    patch.object(banks, "inspect_banks", side_effect=[actor([entry(0xC64)]), actor([])]), \
                    patch.object(banks, "metadata", return_value=detail), \
                    self.assertRaisesRegex(ValueError, "Selected record changed"):
                banks.inspect_pair(SimpleNamespace(identity={}), 1, 2, 0xC64)
