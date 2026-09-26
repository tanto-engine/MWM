# Inspect only Nioh's loaded executable; never request write/debug access.
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
    # Enumerate module names, paths and image ranges through Toolhelp.
    # Close the snapshot even when enumeration fails.
    # Supply executable identity without requesting write access.
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
    # Copy exactly the requested bytes from a read-only process handle.
    # Check both the API result and the actual byte count.
    # Partial reads must fail before callers decode native structures.
    buf = C.create_string_buffer(count)
    n = SIZE()
    ok = kernel.ReadProcessMemory(handle, address, buf, count, C.byref(n))
    if not ok or n.value != count:
        raise OSError(f'Read failed at {address:#x}: {n.value}/{count}; error {C.get_last_error()}')
    return buf.raw


class PROCESSENTRY32W(C.Structure):
    _fields_ = [('dwSize', W.DWORD), ('cntUsage', W.DWORD), ('th32ProcessID', W.DWORD),
                ('th32DefaultHeapID', C.c_size_t), ('th32ModuleID', W.DWORD),
                ('cntThreads', W.DWORD), ('th32ParentProcessID', W.DWORD),
                ('pcPriClassBase', W.LONG), ('dwFlags', W.DWORD), ('szExeFile', W.WCHAR * 260)]


def current_pid():
    # Find the single current Nioh process without a saved PID.
    # Enumerate processes and reject zero or multiple matching executables.
    # Attachment must not guess between concurrent game instances.
    kernel.Process32FirstW.argtypes = [W.HANDLE, C.POINTER(PROCESSENTRY32W)]
    kernel.Process32FirstW.restype = W.BOOL
    kernel.Process32NextW.argtypes = kernel.Process32FirstW.argtypes
    kernel.Process32NextW.restype = W.BOOL
    handle = kernel.CreateToolhelp32Snapshot(2, 0)
    if handle == C.c_void_p(-1).value:
        raise C.WinError(C.get_last_error())
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = C.sizeof(entry)
        matches = []
        okay = kernel.Process32FirstW(handle, C.byref(entry))
        while okay:
            if entry.szExeFile.lower() == 'nioh.exe':
                matches.append(entry.th32ProcessID)
            okay = kernel.Process32NextW(handle, C.byref(entry))
        error = C.get_last_error()
        if error != 18:  # ERROR_NO_MORE_FILES
            raise C.WinError(error)
        if len(matches) != 1:
            raise ValueError(f'Expected exactly one running nioh.exe; found {len(matches)}')
        return matches[0]
    finally:
        kernel.CloseHandle(handle)
