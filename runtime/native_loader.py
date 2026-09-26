# Explicitly load/start or stop the passive research DLL in one guarded process.
#
# No debugger, thread termination, process termination, or remote FreeLibrary.
# Every command requires the target's exact creation FILETIME, not just its PID.
import argparse
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
import os
from pathlib import Path
import struct
import sys

from project_paths import MOD_ROOT
CODE = Path(os.environ.get('TANTO_RUNTIME_CODE', Path(__file__).resolve().parent))
HERE = Path(os.environ.get('NIOH_RUNTIME_HOME', MOD_ROOT/'runtime'))
WORKSPACE = CODE.parent
sys.path.insert(0, str(CODE))
import nioh_memory as memory
from runtime_session import encode_session

K = memory.kernel
NIOH = Path(os.environ.get("NIOH_EXE") or r"C:\Program Files (x86)\Steam\steamapps\common\Nioh\nioh.exe")
NIOH_HASH = "0c3508c6b4d0696d84423949df9faccb3f9c6d93833854e1e17a78d66defc389"
HARNESS = WORKSPACE / "tests" / "native" / "nioh_hook_harness.exe"
START, STOP = "NiohResearchStart", "NiohResearchStop"
PROGRESS = {}


def reset_progress():
    # Start a fresh diagnostic record for one loader command.
    # Clear previous stages and every mutation/completion marker.
    # Cleanup decisions must not inherit facts from an earlier attempt.
    PROGRESS.clear()
    PROGRESS.update(stage="arguments", api=None, mutation_started=False,
                    load_thread_started=False, load_completed=False,
                    export_thread_started=False, export_completed=False)


def stage(name):
    # Record the next loader boundary before crossing it.
    # Update the phase and clear the last API label.
    # Failures report the operation that actually failed.
    PROGRESS.update(stage=name, api=None)


def error_report(error):
    # Expose loader failure provenance to the supervising process.
    # Combine the exception with stage, API and mutation markers.
    # The caller can distinguish preflight rejection from uncertain native work.
    return dict(status="error", message=str(error), **PROGRESS,
                winerror=getattr(error, "winerror", None))


reset_progress()
SIZE = C.c_size_t
K.GetProcessTimes.argtypes = [W.HANDLE] + [C.POINTER(W.FILETIME)] * 4
K.GetProcessTimes.restype = W.BOOL
K.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)]
K.QueryFullProcessImageNameW.restype = W.BOOL
K.GetExitCodeProcess.argtypes = [W.HANDLE, C.POINTER(W.DWORD)]
K.GetExitCodeProcess.restype = W.BOOL
K.GetModuleHandleW.argtypes = [W.LPCWSTR]
K.GetModuleHandleW.restype = W.HMODULE
K.GetProcAddress.argtypes = [W.HMODULE, C.c_char_p]
K.GetProcAddress.restype = C.c_void_p
K.VirtualAllocEx.argtypes = [W.HANDLE, C.c_void_p, SIZE, W.DWORD, W.DWORD]
K.VirtualAllocEx.restype = C.c_void_p
K.VirtualFreeEx.argtypes = [W.HANDLE, C.c_void_p, SIZE, W.DWORD]
K.VirtualFreeEx.restype = W.BOOL
K.WriteProcessMemory.argtypes = [W.HANDLE, C.c_void_p, C.c_void_p, SIZE, C.POINTER(SIZE)]
K.WriteProcessMemory.restype = W.BOOL
K.CreateRemoteThread.argtypes = [W.HANDLE, C.c_void_p, SIZE, C.c_void_p, C.c_void_p, W.DWORD, C.POINTER(W.DWORD)]
K.CreateRemoteThread.restype = W.HANDLE
K.WaitForSingleObject.argtypes = [W.HANDLE, W.DWORD]
K.WaitForSingleObject.restype = W.DWORD
K.GetExitCodeThread.argtypes = [W.HANDLE, C.POINTER(W.DWORD)]
K.GetExitCodeThread.restype = W.BOOL


def checked(ok, api=None):
    # Convert a failed Win32 result into its original Windows error.
    # Record the API name before testing the returned value.
    # Error reporting preserves the native failure instead of substituting defaults.
    if api:
        PROGRESS["api"] = api
    if not ok:
        raise C.WinError(C.get_last_error())
    return ok


def canonical(path):
    # Normalize a path for Windows module identity comparisons.
    # Resolve filesystem aliases and normalize case.
    # Equivalent spelling cannot hide a duplicate loaded module.
    return os.path.normcase(os.path.realpath(path))


def creation_time(handle):
    # Read the target's non-reusable process birth identifier.
    # Combine the two FILETIME halves returned by GetProcessTimes.
    # A PID alone cannot identify the process authorized for this operation.
    times = [W.FILETIME() for _ in range(4)]
    checked(K.GetProcessTimes(handle, *(C.byref(t) for t in times)), "GetProcessTimes")
    return (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime


def validate_target(handle, args):
    # Verify the exact live executable before native operations.
    # Check birth, image path, AMD64 headers, build hash and exit state.
    # Unsupported or replaced targets fail before mutation.
    if creation_time(handle) != args.creation_filetime:
        PROGRESS["api"] = "validate_target.creation_filetime"
        raise ValueError("PID creation FILETIME mismatch")
    pathbuf, count = C.create_unicode_buffer(32768), W.DWORD(32768)
    checked(K.QueryFullProcessImageNameW(handle, 0, pathbuf, C.byref(count)), "QueryFullProcessImageNameW")
    actual_path = Path(pathbuf.value)
    pinned_path = HARNESS if args.harness else Path(os.environ['NIOH_EXE']) if os.environ.get('NIOH_EXE') else None
    PROGRESS["api"] = "validate_target.executable_path"
    if pinned_path is not None and canonical(actual_path) != canonical(pinned_path):
        raise ValueError(f"Target path mismatch; expected {pinned_path}")
    expected_name = HARNESS.name if args.harness else 'nioh.exe'
    if actual_path.name.casefold() != expected_name.casefold():
        raise ValueError("Target executable name mismatch")
    PROGRESS["api"] = "read_executable_build"
    image = actual_path.read_bytes()
    nt = struct.unpack_from("<I", image, 0x3C)[0]
    if image[:2] != b"MZ" or image[nt:nt + 4] != b"PE\0\0" or struct.unpack_from("<H", image, nt + 4)[0] != 0x8664:
        raise ValueError("Expected an AMD64 PE executable")
    digest = hashlib.sha256(image).hexdigest()
    if not args.harness and digest != NIOH_HASH:
        raise ValueError("Nioh executable build SHA-256 mismatch")
    exit_code = W.DWORD()
    checked(K.GetExitCodeProcess(handle, C.byref(exit_code)), "GetExitCodeProcess")
    if exit_code.value != 259:
        raise ValueError("Target has exited")
    return digest


def module_at_path(pid, path):
    # Find a loaded module by its canonical full path.
    # Enumerate target modules and require at most one exact match.
    # A same-named DLL elsewhere must not receive our exports.
    PROGRESS["api"] = "nioh_memory.modules (Toolhelp module enumeration)"
    matches = [m for m in memory.modules(pid) if canonical(m["path"]) == canonical(path)]
    if len(matches) > 1:
        raise ValueError("Ambiguous module path")
    return matches[0] if matches else None


def remote_load_library(pid):
    # Resolve LoadLibraryW in its actual remote owner module.
    # Locate a forwarded local function, then apply its RVA to the matching module.
    # KernelBase forwarding makes a kernel32-base assumption incorrect.
    # GetProcAddress may return a forwarded function in KernelBase, not kernel32.
    kernel32 = checked(K.GetModuleHandleW("kernel32.dll"), "GetModuleHandleW(kernel32.dll)")
    address = checked(K.GetProcAddress(kernel32, b"LoadLibraryW"), "GetProcAddress(LoadLibraryW)")
    PROGRESS["api"] = "nioh_memory.modules (local owner enumeration)"
    owners = [m for m in memory.modules(os.getpid()) if m["base"] <= address < m["base"] + m["size"]]
    if len(owners) != 1:
        raise ValueError("Cannot identify actual LoadLibraryW owner module")
    owner = owners[0]
    remote = module_at_path(pid, owner["path"])
    if remote is None:
        raise ValueError("Target lacks matching LoadLibraryW owner module")
    rva = address - owner["base"]
    if rva >= remote["size"]:
        raise ValueError("LoadLibraryW RVA outside remote owner module")
    return remote["base"] + rva


def remote_export(handle, module, name):
    # Resolve a named export from the loaded target DLL.
    # Read bounded PE export tables and reject invalid or forwarded entries.
    # The callback address must belong to the validated loaded module.
    # Read the loaded DLL's export table, including when already loaded.
    def read(rva, length):
        # Read one RVA-bounded export-table region.
        # Check the requested extent against the module before remote reading.
        # Malformed PE offsets cannot escape the module mapping.
        PROGRESS["api"] = "ReadProcessMemory(export_table)"
        if rva < 0 or length < 0 or rva + length > module["size"]:
            raise ValueError("Export table read outside module")
        return memory.read(handle, module["base"] + rva, length)
    dos = read(0, 64)
    if dos[:2] != b"MZ":
        raise ValueError("Loaded DLL lacks MZ header")
    nt = struct.unpack_from("<I", dos, 60)[0]
    headers = read(nt, 144)
    if headers[:4] != b"PE\0\0" or struct.unpack_from("<H", headers, 4)[0] != 0x8664 or struct.unpack_from("<H", headers, 24)[0] != 0x20B:
        raise ValueError("Loaded DLL is not AMD64 PE32+")
    export_rva, export_size = struct.unpack_from("<II", headers, 136)
    if not export_rva or export_size < 40:
        raise ValueError("DLL lacks export table")
    fields = struct.unpack("<IIHHIIIIIII", read(export_rva, 40))
    functions, names = fields[6], fields[7]
    function_rvas, name_rvas, ordinals = fields[8:11]
    if not 0 < names <= functions <= 10000:
        raise ValueError("Invalid export table counts")
    wanted = name.encode("ascii")
    for i in range(names):
        name_rva = struct.unpack("<I", read(name_rvas + 4 * i, 4))[0]
        value = read(name_rva, min(256, module["size"] - name_rva)).split(b"\0", 1)[0]
        if value != wanted:
            continue
        ordinal = struct.unpack("<H", read(ordinals + 2 * i, 2))[0]
        if ordinal >= functions:
            raise ValueError("Export ordinal outside table")
        rva = struct.unpack("<I", read(function_rvas + 4 * ordinal, 4))[0]
        if not rva or rva >= module["size"] or export_rva <= rva < export_rva + export_size:
            raise ValueError("Invalid or forwarded research export")
        return module["base"] + rva
    raise ValueError(f"Loaded DLL does not export {name}")


class PendingThread(RuntimeError):
    pass


def run_thread(handle, address, parameter, timeout_ms, on_created=None):
    # Call an authorized native entry and observe its completion.
    # Start one remote thread, wait boundedly and retain uncertain execution.
    # A timeout never justifies terminating the game thread or freeing its data.
    tid = W.DWORD()
    thread = checked(K.CreateRemoteThread(handle, None, 0, address, parameter, 0, C.byref(tid)), "CreateRemoteThread")
    PROGRESS["mutation_started"] = True
    if on_created:
        on_created()
    try:
        PROGRESS["api"] = "WaitForSingleObject(remote_thread)"
        wait = K.WaitForSingleObject(thread, timeout_ms)
        if wait != 0:
            # A timeout/failed wait is not proof of completion. Never terminate.
            raise PendingThread(f"Remote thread {tid.value} completion unknown (wait={wait:#x})")
        code = W.DWORD()
        checked(K.GetExitCodeThread(thread, C.byref(code)), "GetExitCodeThread")
        return code.value
    finally:
        K.CloseHandle(thread)


def load_dll(handle, args, dll):
    # Load an exact DLL path while preserving uncertain thread ownership.
    # Allocate/copy the path and free it only after known completion.
    # A pending LoadLibrary call may still reference its argument buffer.
    stage("load_library_resolution")
    loader = remote_load_library(args.pid)
    payload = (str(dll) + "\0").encode("utf-16-le")
    stage("load_library")
    address = checked(K.VirtualAllocEx(handle, None, len(payload), 0x3000, 0x04), "VirtualAllocEx(DLL_path)")
    PROGRESS["mutation_started"] = True
    thread_started = False
    completion_known = False
    def started():
        # Mark the instant native loading acquires the path buffer.
        # Set both local lifetime state and the diagnostic thread-start marker.
        # Cleanup must retain the buffer after an uncertain wait.
        nonlocal thread_started
        thread_started = True
        PROGRESS["load_thread_started"] = True
    try:
        count = SIZE()
        buffer = C.create_string_buffer(payload)
        checked(K.WriteProcessMemory(handle, address, buffer, len(payload), C.byref(count)), "WriteProcessMemory(DLL_path)")
        if count.value != len(payload):
            raise OSError("Incomplete DLL path write")
        validate_target(handle, args)
        run_thread(handle, loader, address, args.timeout_ms, started)
        completion_known = True
        PROGRESS["load_completed"] = True
    except PendingThread as exc:
        raise PendingThread(f"{exc}; retained DLL-path allocation {address:#x} ({len(payload)} bytes)") from exc
    finally:
        if not thread_started or completion_known:
            # Successful cleanup must not replace the API label of an earlier failure.
            freed = K.VirtualFreeEx(handle, address, 0, 0x8000)
            if not freed:
                checked(freed, "VirtualFreeEx(DLL_path)")
    # An x64 HMODULE is not a DWORD: never derive its address from thread exit code.
    stage("load_library_verify")
    module = module_at_path(args.pid, dll)
    if module is None:
        raise RuntimeError("LoadLibraryW finished but exact DLL module is absent")
    return module


def call_export(handle, args, export, payload=None):
    # Pass optional session bytes to an already-resolved native export.
    # Copy the payload, verify the target again and track completion.
    # Startup data stays allocated when the callback may still be reading it.
    # Retain startup data after a timeout: the remote callback may still read it.
    address = None
    thread_started = completion_known = False
    def started():
        # Record that the export callback has started using its argument.
        # Set the local ownership flag and shared diagnostic marker together.
        # Failure handling can distinguish no call from an unresolved call.
        nonlocal thread_started
        thread_started = True
        PROGRESS['export_thread_started'] = True
    try:
        if payload is not None:
            address = checked(K.VirtualAllocEx(handle, None, len(payload), 0x3000, 0x04),
                              'VirtualAllocEx(session_config)')
            PROGRESS['mutation_started'] = True
            count, buffer = SIZE(), C.create_string_buffer(payload)
            checked(K.WriteProcessMemory(handle, address, buffer, len(payload), C.byref(count)),
                    'WriteProcessMemory(session_config)')
            if count.value != len(payload):
                raise OSError('Incomplete runtime session configuration write')
        validate_target(handle, args)
        result = run_thread(handle, export, address, args.timeout_ms, started)
        completion_known = True
        PROGRESS['export_completed'] = True
        return result
    except PendingThread as error:
        if address:
            raise PendingThread(f'{error}; retained session-config allocation {address:#x} ({len(payload)} bytes)') from error
        raise
    finally:
        if address and (not thread_started or completion_known):
            freed = K.VirtualFreeEx(handle, address, 0, 0x8000)
            if not freed:
                checked(freed, 'VirtualFreeEx(session_config)')


def main():
    # Dispatch a validated load/start or stop command.
    # Resolve the exact process, DLL and export before invoking native work.
    # Machine-readable progress lets the supervisor choose recovery safely.
    reset_progress()
    parser = argparse.ArgumentParser(description='Load or stop a researched native runtime in a verified Nioh process.')
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--creation-filetime", type=int, required=True)
    parser.add_argument("--dll", type=Path, required=True)
    parser.add_argument("--harness", action="store_true")
    parser.add_argument("--export", choices=(START, STOP), default=START)
    parser.add_argument('--session-config', type=Path, help='Runtime startup configuration; ignored for Stop')
    parser.add_argument("--timeout-ms", type=int, default=10000)
    args = parser.parse_args()
    if C.sizeof(C.c_void_p) != 8 or not 0 < args.pid <= 0xFFFFFFFF or args.creation_filetime <= 0 or not 100 <= args.timeout_ms <= 60000:
        parser.error("Require 64-bit Python, positive PID/creation FILETIME, and timeout 100..60000 ms")
    PROGRESS["api"] = "resolve_dll_path"
    dll = args.dll.resolve(strict=True)
    if dll.suffix.casefold() != ".dll":
        parser.error("--dll must identify a DLL file")
    payload = None
    if args.export == START and args.session_config is not None:
        payload = encode_session(json.loads(args.session_config.read_text(encoding='utf-8-sig')),
                                 args.pid, args.creation_filetime)
    stage("preflight")
    handle = checked(K.OpenProcess(0x1000, False, args.pid), "OpenProcess(query)")
    try:
        digest = validate_target(handle, args)
    finally:
        K.CloseHandle(handle)
    # Query + read/write/operation + create-thread; never PROCESS_ALL_ACCESS.
    handle = checked(K.OpenProcess(0x1000 | 0x0400 | 0x0010 | 0x0020 | 0x0008 | 0x0002, False, args.pid), "OpenProcess(loader_access)")
    try:
        validate_target(handle, args)
        module = module_at_path(args.pid, dll)
        loaded_now = module is None
        if loaded_now:
            if args.export == STOP:
                raise ValueError("DLL is not loaded; nothing to stop")
            module = load_dll(handle, args, dll)
        stage("export_resolution")
        export = remote_export(handle, module, args.export)
        stage("export_preflight")
        validate_target(handle, args)
        stage("export")
        result = call_export(handle, args, export, payload)
        print(json.dumps({"status": "export_returned", "pid": args.pid, "creation_filetime": str(args.creation_filetime),
                          "mode": "owned_harness" if args.harness else "nioh", "build_sha256": digest,
                          "loaded_now": loaded_now, "export": args.export, "result": result, **PROGRESS}))
        return 0 if result == 0 else 2
    finally:
        K.CloseHandle(handle)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, struct.error) as exc:
        print(json.dumps(error_report(exc)), file=sys.stderr)
        raise SystemExit(1)
