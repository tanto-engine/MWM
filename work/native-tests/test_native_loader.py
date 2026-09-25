"""Pure mocked loader checks: this never opens or starts a target process."""
import importlib.util
from pathlib import Path
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import patch

path = Path(__file__).resolve().parents[2] / "outputs/okatsu-prototype/native_loader.py"
spec = importlib.util.spec_from_file_location("native_loader", path)
loader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(loader)


class FakeKernel:
    def __init__(self, wait=0):
        self.wait = wait
        self.freed = []
        self.closed = []
    def GetModuleHandleW(self, name): return 0x100000
    def GetProcAddress(self, handle, name): return 0x204321
    def VirtualAllocEx(self, *args): return 0x900000
    def VirtualFreeEx(self, handle, address, size, kind):
        self.freed.append(address)
        return True
    def WriteProcessMemory(self, handle, address, buf, count, written):
        written._obj.value = count
        return True
    def CreateRemoteThread(self, handle, attr, stack, address, param, flags, tid):
        tid._obj.value = 7
        return 33
    def WaitForSingleObject(self, handle, timeout): return self.wait
    def GetExitCodeThread(self, handle, code):
        code._obj.value = 0
        return True
    def CloseHandle(self, handle):
        self.closed.append(handle)
        return True


class LoaderTests(unittest.TestCase):
    def setUp(self):
        loader.reset_progress()

    def test_preflight_error_reports_api_without_mutation(self):
        loader.stage('preflight')
        with self.assertRaises(OSError) as caught:
            loader.checked(False, 'OpenProcess(query)')
        report = loader.error_report(caught.exception)
        self.assertEqual((report['stage'], report['api']), ('preflight', 'OpenProcess(query)'))
        self.assertFalse(report['mutation_started'])
        self.assertFalse(report['export_thread_started'])

    def test_forwarded_loadlibrary_uses_actual_owner_and_remote_base(self):
        local = [dict(base=0x100000, size=0x10000, path="kernel32.dll"),
                 dict(base=0x200000, size=0x10000, path="kernelbase.dll")]
        remote = [dict(base=0xA00000, size=0x10000, path="kernel32.dll"),
                  dict(base=0xB00000, size=0x10000, path="kernelbase.dll")]
        with patch.object(loader, "K", FakeKernel()), patch.object(loader.os, "getpid", return_value=1), \
             patch.object(loader.memory, "modules", side_effect=lambda pid: local if pid == 1 else remote):
            self.assertEqual(loader.remote_load_library(2), 0xB04321)

    def test_load_timeout_keeps_argument_memory_and_closes_thread(self):
        kernel = FakeKernel(wait=0x102)
        args = SimpleNamespace(pid=2, timeout_ms=100)
        with patch.object(loader, "K", kernel), patch.object(loader, "remote_load_library", return_value=0xB04321), \
             patch.object(loader, "validate_target", return_value=None):
            with self.assertRaisesRegex(loader.PendingThread, "retained DLL-path allocation"):
                loader.load_dll(1, args, Path("research.dll"))
        self.assertEqual(kernel.freed, [])
        self.assertEqual(kernel.closed, [33])
        self.assertTrue(loader.PROGRESS['mutation_started'])
        self.assertTrue(loader.PROGRESS['load_thread_started'])
        self.assertFalse(loader.PROGRESS['load_completed'])
        self.assertEqual(loader.PROGRESS['api'], 'WaitForSingleObject(remote_thread)')

    def test_wait_failure_also_retains_memory(self):
        kernel = FakeKernel(wait=0xFFFFFFFF)
        args = SimpleNamespace(pid=2, timeout_ms=100)
        with patch.object(loader, "K", kernel), patch.object(loader, "remote_load_library", return_value=0xB04321), \
             patch.object(loader, "validate_target", return_value=None):
            with self.assertRaises(loader.PendingThread):
                loader.load_dll(1, args, Path("research.dll"))
        self.assertEqual(kernel.freed, [])

    def test_completed_load_releases_path_and_uses_enumerated_module(self):
        kernel = FakeKernel()
        module = dict(base=0xABC00000, size=0x10000, path="research.dll")
        args = SimpleNamespace(pid=2, timeout_ms=100)
        with patch.object(loader, "K", kernel), patch.object(loader, "remote_load_library", return_value=0xB04321), \
             patch.object(loader, "validate_target", return_value=None), \
             patch.object(loader, "module_at_path", return_value=module):
            self.assertEqual(loader.load_dll(1, args, Path("research.dll")), module)
        self.assertEqual(kernel.freed, [0x900000])

    def test_loaded_export_is_resolved_from_remote_image(self):
        data = bytearray(0x1000)
        data[:2] = b"MZ"
        struct.pack_into("<I", data, 60, 0x80)
        data[0x80:0x84] = b"PE\0\0"
        struct.pack_into("<H", data, 0x84, 0x8664)
        struct.pack_into("<H", data, 0x98, 0x20B)
        struct.pack_into("<II", data, 0x108, 0x200, 0x100)
        struct.pack_into("<IIHHIIIIIII", data, 0x200, 0, 0, 0, 0, 0, 1, 1, 1, 0x240, 0x250, 0x260)
        struct.pack_into("<I", data, 0x240, 0x500)
        struct.pack_into("<I", data, 0x250, 0x280)
        struct.pack_into("<H", data, 0x260, 0)
        data[0x280:0x280 + len(loader.START)] = loader.START.encode()
        module = dict(base=0x500000, size=len(data))
        with patch.object(loader.memory, "read", side_effect=lambda h, at, size: bytes(data[at - 0x500000:at - 0x500000 + size])):
            self.assertEqual(loader.remote_export(1, module, loader.START), 0x500500)
            struct.pack_into("<I", data, 0x240, 0x290)
            with self.assertRaisesRegex(ValueError, "forwarded"):
                loader.remote_export(1, module, loader.START)


if __name__ == "__main__":
    unittest.main()
