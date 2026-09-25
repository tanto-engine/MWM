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
        self.values = [7, 100, 1, 2, 3, 4, 5, 6, 9, 10, 11, 12, -1, 14, 15, 1, 31, 0, 7]
        self.raw = reader.RECORD.pack(*self.values)
        self.trace = reader.Trace.__new__(reader.Trace)
        self.trace.address = 0x10000

    def test_layout_and_fields(self):
        self.assertEqual(reader.HEADER.size, 128)
        self.assertEqual(reader.RECORD.size, 112)
        result = reader.decode(self.raw, 7)
        self.assertEqual((result['payload'], result['bank'], result['valid_fields']), ('0x6', -1, 31))

    def test_uncommitted_or_reused_slot_rejected(self):
        for at in (0, -1):
            values = self.values.copy()
            values[at] = 0
            self.assertIsNone(reader.decode(reader.RECORD.pack(*values), 7))

    def test_overwrite_after_copy_rejected(self):
        with patch.object(reader.C, 'string_at', side_effect=[self.raw, struct.pack('<q', 519)]):
            self.assertIsNone(self.trace.record(7))

    def test_stable_slot_accepted(self):
        with patch.object(reader.C, 'string_at', side_effect=[self.raw, struct.pack('<q', 7)]):
            self.assertEqual(self.trace.record(7)['input_key'], 10)


if __name__ == '__main__':
    unittest.main()
