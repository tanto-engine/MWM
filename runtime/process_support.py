# One registered supervisor with direct source worker entrypoints.
import ctypes as C
from ctypes import wintypes as W
import os
import json
import subprocess
from pathlib import Path
import sys


def runtime_registry_path():
    # Locate the per-user active-runtime registry.
    # Resolve it beneath LOCALAPPDATA rather than a project checkout.
    # Source and future installed copies can find the same supervisor.
    return Path(os.environ['LOCALAPPDATA']) / 'NiohSkillExpanded' / 'active-runtime.json'


def active_runtime():
    # Find a live supervisor across workspace copies.
    # Check the registered directory and the process creation identity.
    # A reused PID or deleted installation is not treated as active.
    # Discover the singleton's files across source and installed runtime copies.
    from engine_config import read_json
    record = read_json(runtime_registry_path())
    if not isinstance(record, dict) or not isinstance(record.get('runtime_path'), str):
        return None
    if not Path(record['runtime_path']).is_dir() or not process_matches(record):
        return None
    return record


def register_runtime(runtime_path, catalogue_path=None):
    # Advertise the supervisor while its singleton lock is held.
    # Store its birth identity, runtime directory and catalogue location.
    # Other launchers can target the existing instance instead of duplicating it.
    # Called only while PlayLock is held; registry lifetime matches its owner.
    from engine_config import atomic_json
    identity = process_identity()
    if identity is None:
        raise RuntimeError('Cannot identify the launcher process')
    record = dict(identity, runtime_path=str(Path(runtime_path).resolve()))
    if catalogue_path:
        record['catalogue_path'] = str(Path(catalogue_path).resolve())
    atomic_json(runtime_registry_path(), record)
    return record


def unregister_runtime(record):
    # Remove only the registry entry owned by this supervisor.
    # Compare the complete stored record before unlinking it.
    # Shutdown cannot erase a replacement supervisor's registration.
    from engine_config import read_json
    path = runtime_registry_path()
    current = read_json(path)
    if current == record:
        path.unlink(missing_ok=True)


def worker_command(script, *arguments):
    # Build a direct Python invocation for a source worker.
    # Reuse the current interpreter and disable bytecode writes.
    # Paths with spaces remain arguments rather than shell fragments.
    return [sys.executable, '-B', str(script), *map(str, arguments)]


class PlayLock:
    def __init__(self):
        # Enforce one active play supervisor per Windows session.
        # Create a named mutex and reject an already-existing owner.
        # Multiple workspaces cannot independently mutate the same player.
        self.kernel = C.WinDLL('kernel32', use_last_error=True)
        self.kernel.CreateMutexW.argtypes = [C.c_void_p, W.BOOL, W.LPCWSTR]
        self.kernel.CreateMutexW.restype = W.HANDLE
        self.kernel.CloseHandle.argtypes = [W.HANDLE]
        self.handle = self.kernel.CreateMutexW(None, False, 'Local\\NiohSkillExpandedPlaySupervisor_v1')
        error = C.get_last_error()
        if not self.handle:
            raise C.WinError(error)
        if error == 183:
            self.close()
            raise RuntimeError('Another Skill Expanded launcher is already running')

    def close(self):
        # Release this launcher's mutex handle once.
        # Close the live handle and clear the local reference.
        # Cleanup can run after either normal completion or an exception.
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def process_identity(pid=None):
    # Identify a live process beyond its reusable PID.
    # Query creation FILETIME and exit state through a query-only handle.
    # Registry checks cannot attach to a different process after PID reuse.
    kernel = C.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
    kernel.OpenProcess.restype = W.HANDLE
    kernel.GetProcessTimes.argtypes = [W.HANDLE] + [C.POINTER(W.FILETIME)]*4
    kernel.GetProcessTimes.restype = W.BOOL
    kernel.GetExitCodeProcess.argtypes = [W.HANDLE, C.POINTER(W.DWORD)]
    kernel.GetExitCodeProcess.restype = W.BOOL
    kernel.CloseHandle.argtypes = [W.HANDLE]
    pid = pid or os.getpid()
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return None
    try:
        times = [W.FILETIME() for _ in range(4)]
        code = W.DWORD()
        if not kernel.GetProcessTimes(handle, *(C.byref(t) for t in times)) or not kernel.GetExitCodeProcess(handle, C.byref(code)) or code.value != 259:
            return None
        return dict(publisher_pid=pid, publisher_start_filetime=str((times[0].dwHighDateTime << 32) | times[0].dwLowDateTime))
    finally:
        kernel.CloseHandle(handle)


def process_matches(record):
    # Validate the owner recorded in runtime status.
    # Compare its saved birth time with the currently live process.
    # Stale registry data cannot authorize another process.
    if not isinstance(record, dict) or not isinstance(record.get('publisher_pid'), int):
        return False
    actual = process_identity(record['publisher_pid'])
    return actual is not None and actual['publisher_start_filetime'] == str(record.get('publisher_start_filetime'))


def loader_report(stdout, stderr=''):
    # Extract a loader result from either worker output stream.
    # Accept only recognized loader outcomes from valid JSON objects.
    # Keep mutation provenance available when deciding whether to stop a hook.
    for text in (stderr, stdout):
        try:
            value = json.loads(text)
        except (ValueError, TypeError):
            continue
        if isinstance(value, dict) and value.get('status') in ('error', 'export_returned'):
            return value
    return None


class CommandFailure(RuntimeError):
    def __init__(self, name, result):
        # Retain the failing worker name and its loader report.
        # Include stdout and stderr in the exception message.
        # Runtime cleanup needs to distinguish failed start from later failures.
        super().__init__(f'{name} failed ({result.returncode}): {result.stderr.strip()} {result.stdout.strip()}')
        self.name = name
        self.report = loader_report(result.stdout, result.stderr)


def run(command, outdir, name):
    # Run one hidden engine worker and persist both output streams.
    # Raise with the worker identity when its exit code is nonzero.
    # Keep command failures reviewable after the parent exits.
    result = subprocess.run(worker_command(command[0], *command[1:]),
                            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    (outdir / (name+'.stdout.txt')).write_text(result.stdout, encoding='utf8')
    (outdir / (name+'.stderr.txt')).write_text(result.stderr, encoding='utf8')
    if result.returncode:
        raise CommandFailure(name, result)
    return result.stdout
