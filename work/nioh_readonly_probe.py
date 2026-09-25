"""Inspect only Nioh's loaded executable; never request write/debug access."""
import argparse
import ctypes as C
from ctypes import wintypes as W
import json
from pathlib import Path
import re
import struct

kernel = C.WinDLL('kernel32', use_last_error=True)
SIZE = C.c_size_t

class MODULEENTRY32W(C.Structure):
    _fields_ = [('dwSize', W.DWORD), ('th32ModuleID', W.DWORD),
        ('th32ProcessID', W.DWORD), ('GlblcntUsage', W.DWORD),
        ('ProccntUsage', W.DWORD), ('modBaseAddr', C.c_void_p),
        ('modBaseSize', W.DWORD), ('hModule', W.HMODULE),
        ('szModule', W.WCHAR * 256), ('szExePath', W.WCHAR * 260)]

class MEMORY_BASIC_INFORMATION(C.Structure):
    _fields_ = [('BaseAddress', C.c_void_p), ('AllocationBase', C.c_void_p),
        ('AllocationProtect', W.DWORD), ('PartitionId', W.WORD),
        ('RegionSize', SIZE), ('State', W.DWORD), ('Protect', W.DWORD),
        ('Type', W.DWORD)]

kernel.CreateToolhelp32Snapshot.argtypes = [W.DWORD, W.DWORD]
kernel.CreateToolhelp32Snapshot.restype = W.HANDLE
kernel.Module32FirstW.argtypes = [W.HANDLE, C.POINTER(MODULEENTRY32W)]
kernel.Module32FirstW.restype = W.BOOL
kernel.Module32NextW.argtypes = kernel.Module32FirstW.argtypes
kernel.Module32NextW.restype = W.BOOL
kernel.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
kernel.OpenProcess.restype = W.HANDLE
kernel.CloseHandle.argtypes = [W.HANDLE]
kernel.CloseHandle.restype = W.BOOL
kernel.ReadProcessMemory.argtypes = [W.HANDLE, C.c_void_p, C.c_void_p, SIZE, C.POINTER(SIZE)]
kernel.ReadProcessMemory.restype = W.BOOL
kernel.VirtualQueryEx.argtypes = [W.HANDLE, C.c_void_p, C.POINTER(MEMORY_BASIC_INFORMATION), SIZE]
kernel.VirtualQueryEx.restype = SIZE

def modules(pid):
    snap = kernel.CreateToolhelp32Snapshot(0x18, pid)
    if snap == C.c_void_p(-1).value:
        raise C.WinError(C.get_last_error())
    try:
        ent = MODULEENTRY32W()
        ent.dwSize = C.sizeof(ent)
        ok = kernel.Module32FirstW(snap, C.byref(ent))
        if not ok:
            raise C.WinError(C.get_last_error())
        result = []
        while ok:
            result.append(dict(name=ent.szModule, path=ent.szExePath,
                base=ent.modBaseAddr, size=ent.modBaseSize))
            ok = kernel.Module32NextW(snap, C.byref(ent))
        return result
    finally:
        kernel.CloseHandle(snap)

def read(handle, address, count):
    buf = C.create_string_buffer(count)
    n = SIZE()
    ok = kernel.ReadProcessMemory(handle, address, buf, count, C.byref(n))
    if not ok or n.value != count:
        raise OSError(f'Read failed at {address:#x}: {n.value}/{count}; error {C.get_last_error()}')
    return buf.raw

def probe(pid):
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
