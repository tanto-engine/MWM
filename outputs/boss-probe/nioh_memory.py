"""Inspect only Nioh's loaded executable; never request write/debug access."""
import ctypes as C
from ctypes import wintypes as W

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
