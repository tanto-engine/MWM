import hashlib
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'runtime'))
from supervisor import session_binary
from process_support import worker_command


class Portability(unittest.TestCase):
    def test_same_config_uses_same_dll_across_supervisor_restarts(self):
        # Retained native mappings require the original module path on restart.
        # Reuse the same compiled runtime for an unchanged supervisor configuration.
        # Compare runtime selection for repeated launches using one configuration.
        # Transient actor addresses must not require per-session DLL compilation.
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            first, second = folder/'snapshot1.dll', folder/'snapshot2.dll'
            first.write_bytes(b'owned fixture DLL')
            second.write_bytes(first.read_bytes())
            one = session_binary(first, folder/'cache', '0123456789abcdef')
            two = session_binary(second, folder/'cache', '0123456789abcdef')
            self.assertEqual(one, two)
            self.assertEqual(hashlib.sha256(one.read_bytes()).digest(), hashlib.sha256(first.read_bytes()).digest())
            second.write_bytes(b'a different compiled runtime')
            with self.assertRaises(ValueError): session_binary(second, folder/'cache', '0123456789abcdef')
            with self.assertRaises(ValueError): session_binary(first, folder/'cache', '../../not-a-tag')

    def test_source_workers_keep_literal_arguments(self):
        # Preserve script paths and DLL arguments containing spaces.
        # Build a direct invocation using the current Python interpreter.
        # The child must receive the exact arguments without shell parsing.
        script = Path('folder with spaces/native_loader.py')
        self.assertEqual(worker_command(script, '--dll', 'my folder/runtime.dll'),
                         [sys.executable, '-B', str(script), '--dll', 'my folder/runtime.dll'])

    def test_alternate_steam_library_keeps_exact_build_guard(self):
        # Preserve the exact-build guard when the Steam library path differs.
        # Resolve the game from an alternate installation while validating its supported image.
        # Directory flexibility must never disable executable compatibility checking.
        alternate = ROOT/'work/Alternate Steam Library/nioh.exe'
        with patch.dict(os.environ, {'NIOH_EXE': str(alternate)}):
            spec = importlib.util.spec_from_file_location('alternate_loader', ROOT/'runtime/native_loader.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.assertEqual(module.NIOH, alternate)
            self.assertEqual(module.NIOH_HASH, '0c3508c6b4d0696d84423949df9faccb3f9c6d93833854e1e17a78d66defc389')
