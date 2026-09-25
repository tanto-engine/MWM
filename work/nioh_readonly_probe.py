# Inspect only Nioh's loaded executable; never request write/debug access.
import argparse
import ctypes as C
from ctypes import wintypes as W
import json
from pathlib import Path
import re
import struct

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'outputs/boss-probe'))
from nioh_memory import kernel, modules, read, MEMORY_BASIC_INFORMATION

def probe(pid):
    # Search loaded executable sections for the researched commit-byte pattern.
    # Read through query-only process access and retain unreadable spans.
    # Produce candidate evidence without installing a hook or modifying code.
    mods = modules(pid)
    main = [m for m in mods if m['name'].lower() == 'nioh.exe']
    if len(main) != 1:
        raise ValueError('Exactly one nioh.exe module required')
    main = main[0]
    handle = kernel.OpenProcess(0x0410, False, pid)  # QUERY_INFORMATION | VM_READ only
    if not handle:
        raise C.WinError(C.get_last_error())
    try:
        base = main['base']
        header = read(handle, base, 4096)
        pe = struct.unpack_from('<I', header, 0x3c)[0]
        assert header[pe:pe+4] == b'PE\0\0'
        machine, sections = struct.unpack_from('<HH', header, pe+4)
        assert machine == 0x8664
        optional_size = struct.unpack_from('<H', header, pe+20)[0]
        section_start = pe+24+optional_size
        executable_sections = []
        matches = []
        unreadable = []
        scanned = 0
        pattern = re.compile(b'\x48\x83\x7b\x58\x00\x74.', re.DOTALL)
        for i in range(sections):
            s = section_start+40*i
            name = header[s:s+8].rstrip(b'\0').decode('ascii')
            size, rva = struct.unpack_from('<II', header, s+8)
            flags = struct.unpack_from('<I', header, s+36)[0]
            if not flags & 0x20000000:
                continue
            executable_sections.append(dict(name=name, rva=hex(rva), size=size))
            cursor, end = base+rva, base+rva+size
            tail = b''
            while cursor < end:
                mbi = MEMORY_BASIC_INFORMATION()
                if not kernel.VirtualQueryEx(handle, cursor, C.byref(mbi), C.sizeof(mbi)):
                    raise C.WinError(C.get_last_error())
                stop = min(end, mbi.BaseAddress+mbi.RegionSize, cursor+1024*1024)
                if stop <= cursor:
                    raise RuntimeError('Invalid memory region extent')
                readable = mbi.State == 0x1000 and not mbi.Protect & 0x101
                if not readable:
                    unreadable.append(dict(rva=hex(cursor-base), size=stop-cursor))
                    tail = b''
                    cursor = stop
                    continue
                try:
                    data = read(handle, cursor, stop-cursor)
                except OSError as e:
                    unreadable.append(dict(rva=hex(cursor-base), size=stop-cursor, reason=str(e)))
                    tail = b''
                    cursor = stop
                    continue
                combined = tail+data
                for m in pattern.finditer(combined):
                    address = cursor-len(tail)+m.start()
                    exact = combined[m.start():m.start()+7] == bytes.fromhex('48 83 7B 58 00 74 10')
                    matches.append(dict(rva=hex(address-base), address=hex(address),
                        exact_old_pattern=exact,
                        code_context=read(handle, address-16, 80).hex(' ')))
                tail = combined[-6:]
                scanned += len(data)
                cursor = stop
        return dict(pid=pid, access='QUERY_INFORMATION | VM_READ', game_module=main,
            executable_sections=executable_sections, bytes_scanned=scanned,
            unreadable_ranges=unreadable, old_pattern_candidates=matches,
            loaded_modules=[dict(name=m['name'], path=m['path']) for m in mods])
    finally:
        kernel.CloseHandle(handle)

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--pid',type=int,required=True)
    p.add_argument('--output',type=Path,required=True)
    args = p.parse_args()
    result = probe(args.pid)
    args.output.write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k!='loaded_modules'},indent=2))
    print('Loaded modules:',len(result['loaded_modules']))
