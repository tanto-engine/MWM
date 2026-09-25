import importlib.util
from pathlib import Path
import struct
import unittest
from unittest.mock import patch

path = Path(__file__).resolve().parents[2] / 'outputs/okatsu-prototype/trace_reader.py'
spec = importlib.util.spec_from_file_location('trace_reader', path)
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)


class ReaderTests(unittest.TestCase):
    def setUp(self):
        # Pack a complete trace record with matching sequence markers.
        # Create a Trace object without opening a shared mapping.
        # Owned byte copies can exercise overwrite detection and field decoding safely.
        self.values = [7, 100, 1, 2, 3, 4, 5, 6, 9, 10, 11, 12, -1, 14, 15, 1, 31, 0, 7]
        self.raw = reader.RECORD.pack(*self.values)
        self.trace = reader.Trace.__new__(reader.Trace)
        self.trace.address = 0x10000

    def test_layout_and_fields(self):
        # Decode the complete trace layout and signed native fields correctly.
        # Unpack one fully populated owned trace record.
        # Signed fields, pointer order and sequence markers must match the native binary contract.
        self.assertEqual(reader.HEADER.size, 128)
        self.assertEqual(reader.RECORD.size, 112)
        result = reader.decode(self.raw, 7)
        self.assertEqual((result['payload'], result['bank'], result['valid_fields']), ('0x6', -1, 31))

    def test_uncommitted_or_reused_slot_rejected(self):
        # Reject unpublished records and slots already reused by the producer.
        # Present odd or mismatched sequence markers for the requested ring position.
        # The reader must reject unpublished data and slots already reused by a newer record.
        for at in (0, -1):
            values = self.values.copy()
            values[at] = 0
            self.assertIsNone(reader.decode(reader.RECORD.pack(*values), 7))

    def test_overwrite_after_copy_rejected(self):
        # Reject a slot overwritten between the payload copy and final marker check.
        # Change the ring sequence after copying an otherwise coherent record.
        # A post-copy recheck must catch concurrent overwrite before evidence is exposed.
        with patch.object(reader.C, 'string_at', side_effect=[self.raw, struct.pack('<q', 519)]):
            self.assertIsNone(self.trace.record(7))

    def test_stable_slot_accepted(self):
        # Accept only a stable fully committed trace record.
        # Keep both sequence markers stable across the owned record copy.
        # The race guards must still permit a complete current record.
        with patch.object(reader.C, 'string_at', side_effect=[self.raw, struct.pack('<q', 7)]):
            self.assertEqual(self.trace.record(7)['input_key'], 10)
