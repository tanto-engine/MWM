"""Offline lookup regressions based on the saved native disassembly."""
from pathlib import Path
import struct
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "outputs" / "boss-probe"))
import action_banks as banks


def entry(key, pointer=0x30000, enabled=1, position=0):
    return dict(key_u32=key, key_hex=f"0x{key:08X}", descriptor=hex(pointer),
                enabled_byte=enabled, payload="0x50000", position=position)


def actor(*records):
    return {"banks": [{"index": i, "address": hex(0x20000 + i * 0x1000), "records": rows}
                      for i, rows in enumerate(records)]}


def metadata(key=0xC64, enabled=1, payload=0x50000, targets=()):
    raw = bytearray(0xD0)
    struct.pack_into("<I", raw, 0, key)
    struct.pack_into("<Q", raw, 0x20, payload)
    raw[0x40] = enabled
    return {"descriptor_bytes": raw.hex(),
            "transition_entries": [{"target_key_0x14_i16": target} for target in targets]}


class FakeGame:
    def __init__(self, change=None):
        self.change = change
        self.snapshots = 0
        self.identity = {"pid": 123}
        header = bytearray(0x138)
        struct.pack_into("<QI", header, 0x128, 0x21000, 2)
        self.pieces = {0x20000: header, 0x21000: struct.pack("<QQ", 0, 0x30000),
                       0x30000: bytes.fromhex(metadata()["descriptor_bytes"])}

    def snapshot(self, address):
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
        for base, raw in self.pieces.items():
            if base <= address and address + count <= base + len(raw):
                result = bytes(raw[address - base:address - base + count])
                if address == 0x20128 and self.change == "header":
                    result = struct.pack("<QI", 0x21000, 3)
                return result
        raise AssertionError(f"Unexpected fixture read: {address:#x}/{count}")


class NativeLookupTests(unittest.TestCase):
    def test_full_dword_key_is_not_truncated_to_sixteen_bits(self):
        source = actor([entry(0x12340C64, 0x30000), entry(0xC64, 0x40000)])
        self.assertEqual(banks.resolve(source, 0xC64)["descriptor"], "0x40000")
        self.assertEqual(banks.resolve(source, 0x12340C64)["descriptor"], "0x30000")

    def test_first_enabled_match_wins_in_bank_then_array_order(self):
        source = actor([entry(7, 0x30000), entry(7, 0x31000, position=1)],
                       [entry(7, 0x40000)], [entry(7, 0x50000)])
        result = banks.resolve(source, 7)
        self.assertEqual((result["bank_index"], result["descriptor"]), (0, "0x30000"))

    def test_zero_disabled_is_skipped_and_nonzero_is_enabled(self):
        source = actor([entry(7, enabled=0)], [entry(7, 0x40000, enabled=255)])
        result = banks.resolve(source, 7)
        self.assertEqual((result["bank_index"], result["enabled_byte"]), (1, 255))

    def test_all_disabled_or_absent_does_not_resolve(self):
        self.assertIsNone(banks.resolve(actor([], [entry(7, enabled=0)], []), 7))

    def test_out_of_dword_range_is_rejected(self):
        for key in (-1, 0x100000000):
            with self.subTest(key=key), self.assertRaises(ValueError):
                banks.resolve(actor([]), key)

    def test_inspection_skips_null_slots_and_preserves_positions(self):
        result = banks.inspect_banks(FakeGame(), 0x10000)
        self.assertEqual([bank["index"] for bank in result["banks"]], [0, 1, 2])
        self.assertEqual(result["banks"][0]["records"][0]["position"], 1)
        self.assertEqual(result["banks"][0]["records"][0]["key_u32"], 0xC64)
        self.assertIn("not an atomic snapshot", result["consistency"])

    def test_inspection_rejects_header_context_or_owner_changes(self):
        for change in ("header", "context", "owner"):
            with self.subTest(change=change), self.assertRaises(ValueError):
                banks.inspect_banks(FakeGame(change), 0x10000)

    def test_signed_transition_keys_are_sign_extended_and_minus_one_rejected(self):
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
        for detail in (metadata(key=0xC65), metadata(enabled=0), metadata(payload=0x51000)):
            with self.subTest(detail=detail), \
                    patch.object(banks, "inspect_banks", side_effect=[actor([entry(0xC64)]), actor([])]), \
                    patch.object(banks, "metadata", return_value=detail), \
                    self.assertRaisesRegex(ValueError, "Selected record changed"):
                banks.inspect_pair(SimpleNamespace(identity={}), 1, 2, 0xC64)


if __name__ == "__main__":
    unittest.main(verbosity=2)
