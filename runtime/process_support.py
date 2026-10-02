# One registered supervisor with direct source worker entrypoints.
import ctypes as C
from ctypes import wintypes as W
import os
import json
import subprocess
from pathlib import Path
import sys


def runtime_registry_path():
    # Source checkouts and installed releases share one per-user owner registry.
    return Path(os.environ['LOCALAPPDATA']) / 'NiohSkillExpanded' / 'active-runtime.json'


def active_runtime():
    # A retained registry file is live only while its process birth still matches.
    from engine_config import read_json
    record = read_json(runtime_registry_path())
    if not isinstance(record, dict) or not isinstance(record.get('runtime_path'), str):
        return None
    if not Path(record['runtime_path']).is_dir() or not process_matches(record):
        return None
    return record


def register_runtime(runtime_path, catalogue_path=None):
    # The caller holds PlayLock until unregister_runtime completes.
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
    # A departing supervisor must not erase a replacement owner's registration.
    from engine_config import read_json
    path = runtime_registry_path()
    current = read_json(path)
    if current == record:
        path.unlink(missing_ok=True)


def worker_command(script, *arguments):
    # Frozen releases dispatch workers through the EXE; source builds use Python.
    if getattr(sys, 'frozen', False):
        return [sys.executable, '--worker', Path(script).stem, *map(str, arguments)]
    return [sys.executable, '-B', str(script), *map(str, arguments)]


class PlayLock:
    def __init__(self):
        # The named handle, rather than mutex acquisition, defines ownership.
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
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def process_identity(pid=None):
    # Creation FILETIME distinguishes a live owner from a reused PID.
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
    if not isinstance(record, dict) or not isinstance(record.get('publisher_pid'), int):
        return False
    actual = process_identity(record['publisher_pid'])
    return actual is not None and actual['publisher_start_filetime'] == str(record.get('publisher_start_filetime'))


def loader_report(stdout, stderr=''):
    # Only recognized reports can establish whether a failed Start mutated Nioh.
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
        super().__init__(f'{name} failed ({result.returncode}): {result.stderr.strip()} {result.stdout.strip()}')
        self.name = name
        self.report = loader_report(result.stdout, result.stderr)


def run(command, outdir, name):
    # Persist both streams before raising so failed exports remain diagnosable.
    result = subprocess.run(worker_command(command[0], *command[1:]),
                            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    (outdir / (name+'.stdout.txt')).write_text(result.stdout, encoding='utf8')
    (outdir / (name+'.stderr.txt')).write_text(result.stderr, encoding='utf8')
    if result.returncode:
        raise CommandFailure(name, result)
    return result.stdout
