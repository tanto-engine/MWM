"""Offline PE/disassembly helpers for this exact Nioh build."""
import bisect
import hashlib
import json
from pathlib import Path
import struct
import sys
import os
sys.path.insert(0, str(Path(__file__).parent / 'analysisdeps'))
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

EXE = Path(os.environ.get('NIOH_EXE', r'C:\Program Files (x86)\Steam\steamapps\common\Nioh\nioh.exe'))
HASH = '0c3508c6b4d0696d84423949df9faccb3f9c6d93833854e1e17a78d66defc389'


class Native:
    def __init__(self):
        self.file = EXE.read_bytes()
        assert hashlib.sha256(self.file).hexdigest() == HASH
        pe = struct.unpack_from('<I', self.file, 0x3c)[0]
        count = struct.unpack_from('<H', self.file, pe + 6)[0]
        self.base = struct.unpack_from('<Q', self.file, pe + 24 + 24)[0]
        sections = pe + 24 + struct.unpack_from('<H', self.file, pe + 20)[0]
        self.sections = []
        for i in range(count):
            at = sections + i * 40
            self.sections.append((self.file[at:at+8].rstrip(b'\0').decode(),
                                  *struct.unpack_from('<IIII', self.file, at+8)))
        pdata = next(s for s in self.sections if s[0] == '.pdata')
        self.functions = list(struct.iter_unpack('<III', self.file[pdata[4]:pdata[4]+pdata[1]]))
        self.begins = [f[0] for f in self.functions]
        self.cs = Cs(CS_ARCH_X86, CS_MODE_64)
        self.cs.detail = True
        live = Path(__file__).parent / 'live-text.bin'
        self.live_text = live.read_bytes() if live.exists() else None
        if self.live_text is not None:
            info = json.loads(live.with_name('live-text-identity.json').read_text())
            assert info['build_sha256'] == HASH and info['size'] == len(self.live_text)
            self.live_text_rva = info['rva']

    def bytes(self, rva, size):
        if self.live_text is not None and self.live_text_rva <= rva and rva + size <= self.live_text_rva + len(self.live_text):
            at = rva-self.live_text_rva
            return self.live_text[at:at+size]
        for _, virtual_size, start, raw_size, raw in self.sections:
            if start <= rva and rva + size <= start + raw_size:
                at = raw + rva - start
                return self.file[at:at+size]
        raise ValueError(f'Not in a file-backed section: {rva:x}/{size:x}')

    def function(self, rva):
        i = bisect.bisect_right(self.begins, rva) - 1
        if i >= 0 and self.functions[i][0] <= rva < self.functions[i][1]:
            return self.functions[i]
        return (rva, rva + 96, 0)  # leaf function; bounded preview, not a size claim

    def instructions(self, rva):
        start, end, _ = self.function(rva)
        return list(self.cs.disasm(self.bytes(start, end-start), start))

    def text(self, rva):
        return '\n'.join(f'{i.address:08x}  {i.mnemonic:8} {i.op_str}' for i in self.instructions(rva))

    def vtable(self, rva, count):
        return [p - self.base for p in struct.unpack('<'+'Q'*count, self.bytes(rva, count*8))]


if __name__ == '__main__':
    native = Native()
    for arg in sys.argv[1:]:
        if ':' in arg:
            start, end = [int(x, 0) for x in arg.split(':')]
            print('\n'.join(f'{a:08x} {m:8} {s}' for a, _, m, s in native.cs.disasm_lite(native.bytes(start, end-start), start)))
        else:
            print(native.text(int(arg, 0)))
