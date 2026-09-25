import importlib.util
import hashlib
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
        # Configure a remote-thread wait outcome without opening any process.
        # Track released argument addresses and closed handles separately.
        # Timeout tests must distinguish thread lifetime from handle lifetime.
        self.wait = wait
        self.freed = []
        self.closed = []
    def GetModuleHandleW(self, name):
        # Return a fixed local module base for export resolution.
        # Keep it distinct from the module that owns the forwarded procedure.
        # The loader must not compute a forwarded export offset from the wrong image.
        return 0x100000
    def GetProcAddress(self, handle, name):
        # Place the resolved procedure inside a different local module.
        # Return its fixture address without resolving a real operating-system export.
        # Forwarded LoadLibraryW must use its actual owner when rebasing remotely.
        return 0x204321
    def VirtualAllocEx(self, *args):
        # Return a fixed remote argument address as fixture data.
        # Allocate no memory in another process.
        # Tests can inspect argument-retention policy without performing remote mutation.
        return 0x900000
    def VirtualFreeEx(self, handle, address, size, kind):
        # Record every attempted remote argument release.
        # Return success without freeing any operating-system allocation.
        # A still-running remote thread must keep its argument buffer alive.
        self.freed.append(address)
        return True
    def WriteProcessMemory(self, handle, address, buf, count, written):
        # Acknowledge exactly the supplied fixture byte count.
        # Mutate only the caller-owned written-count output parameter.
        # Loader validation can run without writing to a target process.
        written._obj.value = count
        return True
    def CreateRemoteThread(self, handle, attr, stack, address, param, flags, tid):
        # Return a fake thread handle and populate its thread id.
        # Create no operating-system thread and execute no injected code.
        # Lifetime tests exercise the loader's branch decisions in owned Python state.
        tid._obj.value = 7
        return 33
    def WaitForSingleObject(self, handle, timeout):
        # Return the scenario's selected native wait result.
        # Keep completion, timeout and wait failure independently configurable.
        # The loader may release argument memory only after known completion.
        return self.wait
    def GetExitCodeThread(self, handle, code):
        # Report a completed export with a zero result.
        # Write the result through the provided ctypes output object.
        # Tests separate successful thread completion from the module-enumeration outcome.
        code._obj.value = 0
        return True
    def CloseHandle(self, handle):
        # Record handle closure without closing any real object.
        # Keep the list separate from remote argument-memory releases.
        # Closing a thread handle does not prove its argument memory is safe to free.
        self.closed.append(handle)
        return True


class LoaderTests(unittest.TestCase):
    def setUp(self):
        # Reset the loader's mutation-progress report before each case.
        # Discard state from prior simulated export attempts.
        # Preflight failures must never inherit another test's mutation_started flag.
        loader.reset_progress()

    def test_preflight_error_reports_api_without_mutation(self):
        # Report preflight API failure before allocating or starting native work.
        # Fail process access before remote allocation or thread creation.
        # The structured error must identify the failing API and prove mutation never started.
        loader.stage('preflight')
        with self.assertRaises(OSError) as caught:
            loader.checked(False, 'OpenProcess(query)')
        report = loader.error_report(caught.exception)
        self.assertEqual((report['stage'], report['api']), ('preflight', 'OpenProcess(query)'))
        self.assertFalse(report['mutation_started'])
        self.assertFalse(report['export_thread_started'])

    def test_forwarded_loadlibrary_uses_actual_owner_and_remote_base(self):
        # Resolve forwarded LoadLibrary through its actual owner module and remote base.
        # Resolve LoadLibraryW inside a different local image and rebase that owner remotely.
        # Forwarded exports cannot use the originally requested module's base address.
        local = [dict(base=0x100000, size=0x10000, path="kernel32.dll"),
                 dict(base=0x200000, size=0x10000, path="kernelbase.dll")]
        remote = [dict(base=0xA00000, size=0x10000, path="kernel32.dll"),
                  dict(base=0xB00000, size=0x10000, path="kernelbase.dll")]
        with patch.object(loader, "K", FakeKernel()), patch.object(loader.os, "getpid", return_value=1), \
             patch.object(loader.memory, "modules", side_effect=lambda pid: (
                 # Choose the local or remote module inventory from the requested PID.
                 # Keep different image bases for the two address spaces.
                 # Forwarded export rebasing must use the corresponding module owner in each process.
                 local if pid == 1 else remote
             )):
            self.assertEqual(loader.remote_load_library(2), 0xB04321)

    def test_load_timeout_keeps_argument_memory_and_closes_thread(self):
        # Retain remote argument memory when load completion times out.
        # Return a remote-thread timeout after the path argument was allocated.
        # The thread handle may close, but the still-running thread must retain its argument buffer.
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
        # Retain remote argument memory when the wait itself fails.
        # Fail the wait operation after remote execution begins.
        # Unknown completion is not permission to free memory the target may still read.
        kernel = FakeKernel(wait=0xFFFFFFFF)
        args = SimpleNamespace(pid=2, timeout_ms=100)
        with patch.object(loader, "K", kernel), patch.object(loader, "remote_load_library", return_value=0xB04321), \
             patch.object(loader, "validate_target", return_value=None):
            with self.assertRaises(loader.PendingThread):
                loader.load_dll(1, args, Path("research.dll"))
        self.assertEqual(kernel.freed, [])

    def test_completed_load_releases_path_and_uses_enumerated_module(self):
        # Release completed load arguments and trust the enumerated module identity.
        # Complete remote loading and supply the loaded module through enumeration.
        # The path buffer may be freed only after completion and the module address must be verified.
        kernel = FakeKernel()
        module = dict(base=0xABC00000, size=0x10000, path="research.dll")
        args = SimpleNamespace(pid=2, timeout_ms=100)
        with patch.object(loader, "K", kernel), patch.object(loader, "remote_load_library", return_value=0xB04321), \
             patch.object(loader, "validate_target", return_value=None), \
             patch.object(loader, "module_at_path", return_value=module):
            self.assertEqual(loader.load_dll(1, args, Path("research.dll")), module)
        self.assertEqual(kernel.freed, [0x900000])

    def test_loaded_export_is_resolved_from_remote_image(self):
        # Resolve an export against the loaded remote image rather than a local address.
        # Parse export data from an owned synthetic remote PE image.
        # Export resolution must honor the loaded image layout instead of assuming local addresses match.
        data = bytearray(0x1000)
        data[:2] = b"MZ"
        # e_lfanew selects the owned PE header; 0x108 is that PE32+ optional
        # header's export-directory entry, whose fields reference RVAs below.
        struct.pack_into("<I", data, 60, 0x80)
        data[0x80:0x84] = b"PE\0\0"
        struct.pack_into("<H", data, 0x84, 0x8664)
        struct.pack_into("<H", data, 0x98, 0x20B)
        struct.pack_into("<II", data, 0x108, 0x200, 0x100)
        # One export uses separate function, name and ordinal tables. Moving
        # its function RVA inside 0x200..0x300 makes it a forwarded export.
        struct.pack_into("<IIHHIIIIIII", data, 0x200, 0, 0, 0, 0, 0, 1, 1, 1, 0x240, 0x250, 0x260)
        struct.pack_into("<I", data, 0x240, 0x500)
        struct.pack_into("<I", data, 0x250, 0x280)
        struct.pack_into("<H", data, 0x260, 0)
        data[0x280:0x280 + len(loader.START)] = loader.START.encode()
        module = dict(base=0x500000, size=len(data))
        with patch.object(loader.memory, "read", side_effect=lambda h, at, size: (
            # Read bytes from the owned synthetic remote PE image.
            # Translate its fixture base into a Python byte-array slice.
            # Remote export parsing must be exercised without ReadProcessMemory access.
            bytes(data[at - 0x500000:at - 0x500000 + size])
        )):
            self.assertEqual(loader.remote_export(1, module, loader.START), 0x500500)
            struct.pack_into("<I", data, 0x240, 0x290)
            with self.assertRaisesRegex(ValueError, "forwarded"):
                loader.remote_export(1, module, loader.START)

    def test_default_attachment_accepts_alternate_installation_with_exact_build(self):
        # Accept another installation path only when its executable build matches exactly.
        # Return the supported executable from another Steam library directory.
        # Installation portability must retain the exact executable hash and process-liveness guards.
        image = bytearray(256)
        image[:2] = b'MZ'
        struct.pack_into('<I', image, 60, 128)
        image[128:132] = b'PE\0\0'
        struct.pack_into('<H', image, 132, 0x8664)
        digest = hashlib.sha256(image).hexdigest()
        class TargetKernel:
            path = r'D:\Games\SteamLibrary\Nioh\nioh.exe'
            def QueryFullProcessImageNameW(self, handle, flags, path, size):
                # Return the scenario's alternate installation path.
                # Write only the supplied ctypes path buffer.
                # Attachment should verify the executable build instead of assuming one Steam directory.
                path.value = self.path
                return True
            def GetExitCodeProcess(self, handle, code):
                # Report the fixture process as STILL_ACTIVE.
                # Fill the caller's output value without opening a process.
                # The alternate-installation case can reach exact-build validation deterministically.
                code._obj.value = 259
                return True
        kernel = TargetKernel()
        args = SimpleNamespace(creation_filetime=1234, harness=False)
        with patch.object(loader, 'K', kernel), patch.object(loader, 'creation_time', return_value=1234), \
             patch.object(Path, 'read_bytes', return_value=bytes(image)), \
             patch.object(loader, 'NIOH_HASH', digest), patch.dict(loader.os.environ, {}, clear=True):
            self.assertEqual(loader.validate_target(1, args), digest)
            kernel.path = r'D:\Games\SteamLibrary\Nioh\other.exe'
            with self.assertRaisesRegex(ValueError, 'name mismatch'):
                loader.validate_target(1, args)
            kernel.path = r'D:\Games\SteamLibrary\Nioh\nioh.exe'
            with patch.object(loader, 'NIOH_HASH', '0' * 64):
                with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
                    loader.validate_target(1, args)
            with patch.dict(loader.os.environ, {'NIOH_EXE': r'C:\Explicit\nioh.exe'}):
                with self.assertRaisesRegex(ValueError, 'path mismatch'):
                    loader.validate_target(1, args)
