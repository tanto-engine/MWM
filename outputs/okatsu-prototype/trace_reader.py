"""Read the native observer's existing shared-memory trace; no game access."""
import argparse
import ctypes as C
from ctypes import wintypes as W
import json
from pathlib import Path
import struct
import time

HEADER = struct.Struct('<IIIIqqqiiQQ64x')
RECORD = struct.Struct('<qqQQQQQQIIIIiiiIIIq')
CAPACITY = 512
SIZE = HEADER.size + CAPACITY * RECORD.size


def decode(raw, expected):
    values = RECORD.unpack(raw)
    if values[0] != expected or values[-1] != expected:
        return None
    keys = ('sequence', 'qpc', 'actor', 'owner', 'context', 'before', 'after', 'payload',
            'thread_id', 'input_key', 'before_key', 'after_key', 'bank', 'motion_key',
            'timing_key', 'native_result', 'valid_fields', 'reserved', 'sequence_end')
    result = dict(zip(keys, values))
    for key in ('actor', 'owner', 'context', 'before', 'after', 'payload'):
        result[key] = hex(result[key])
    return result


class Trace:
    def __init__(self, pid, prefix='NiohResearchTrace_v1', tag=None):
        if prefix not in ('NiohResearchTrace_v1', 'NiohDispatchTrace_v1', 'NiohBossTrace_v1', 'NiohBossRepeatTrace_v1', 'NiohBossRepeatTrace_v2'):
            raise ValueError('Unknown trace mapping prefix')
        if prefix.endswith('_v2') and (not isinstance(tag, str) or len(tag) != 16 or any(c not in '0123456789abcdef' for c in tag)):
            raise ValueError('Repeat v2 requires a configuration tag')
        self.kernel = C.WinDLL('kernel32', use_last_error=True)
        self.kernel.OpenFileMappingW.argtypes = [W.DWORD, W.BOOL, W.LPCWSTR]
        self.kernel.OpenFileMappingW.restype = W.HANDLE
        self.kernel.MapViewOfFile.argtypes = [W.HANDLE, W.DWORD, W.DWORD, W.DWORD, C.c_size_t]
        self.kernel.MapViewOfFile.restype = C.c_void_p
        self.kernel.UnmapViewOfFile.argtypes = [C.c_void_p]
        self.kernel.UnmapViewOfFile.restype = W.BOOL
        self.kernel.CloseHandle.argtypes = [W.HANDLE]
        self.kernel.CloseHandle.restype = W.BOOL
        self.handle = self.kernel.OpenFileMappingW(4, False, f'Local\\{prefix}_{pid}' + (f'_{tag}' if prefix.endswith('_v2') else ''))
        if not self.handle:
            raise C.WinError(C.get_last_error())
        self.address = self.kernel.MapViewOfFile(self.handle, 4, 0, 0, SIZE)
        if not self.address:
            error = C.get_last_error()
            self.kernel.CloseHandle(self.handle)
            self.handle = None
            raise C.WinError(error)
        try:
            self.header()
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.address:
            self.kernel.UnmapViewOfFile(self.address)
            self.address = None
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None

    def header(self):
        values = HEADER.unpack(C.string_at(self.address, HEADER.size))
        if values[:4] != (0x3152494e, 1, CAPACITY, RECORD.size) or values[4] <= 0:
            raise ValueError('Unexpected trace protocol header')
        return dict(frequency=values[4], written=values[5], dropped=values[6], status=values[7],
                    enabled=values[8], hook_address=hex(values[9]), module_base=hex(values[10]))

    def record(self, sequence):
        address = self.address + HEADER.size + (sequence-1) % CAPACITY * RECORD.size
        raw = C.string_at(address, RECORD.size)
        result = decode(raw, sequence)
        # Recheck after copy to reject a slot overwritten during the copy.
        if struct.unpack('<q', C.string_at(address, 8))[0] != sequence:
            return None
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--seconds', type=float, default=0)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if not 0 <= args.seconds <= 120:
        parser.error('Duration must be 0..120 seconds')
    if args.out.exists():
        parser.error('Output already exists')
    trace = Trace(args.pid)
    copied = gaps = races = 0
    actors, threads = set(), set()
    try:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open('x', encoding='utf8') as output:
            header = trace.header()
            output.write(json.dumps(dict(kind='session', pid=args.pid, **header)) + '\n')
            next_sequence = max(1, header['written'] - CAPACITY + 1)
            started = time.perf_counter()
            while True:
                header = trace.header()
                oldest = max(1, header['written'] - CAPACITY + 1)
                if next_sequence < oldest:
                    gaps += oldest-next_sequence
                    output.write(json.dumps(dict(kind='overwritten', first=next_sequence, next=oldest)) + '\n')
                    next_sequence = oldest
                for sequence in range(next_sequence, header['written']+1):
                    record = trace.record(sequence)
                    if record is None:
                        races += 1
                        output.write(json.dumps(dict(kind='slot_race', sequence=sequence)) + '\n')
                    else:
                        output.write(json.dumps(dict(kind='action_call', **record)) + '\n')
                        actors.add(record['actor']); threads.add(record['thread_id']); copied += 1
                    next_sequence = sequence+1
                if time.perf_counter() - started >= args.seconds:
                    break
                time.sleep(0.02)
            summary = dict(kind='summary', copied=copied, overwritten=gaps, slot_races=races,
                           actors=sorted(actors), thread_ids=sorted(threads), **trace.header())
            output.write(json.dumps(summary) + '\n')
            print(json.dumps(summary, indent=2))
    finally:
        trace.close()


if __name__ == '__main__':
    main()
