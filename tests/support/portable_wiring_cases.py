import hashlib
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'outputs/okatsu-prototype'))
from play_okatsu import session_binary
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

    def test_frozen_workers_use_exe_entrypoint_with_literal_arguments(self):
        # Forward literal worker arguments through the eventual frozen entrypoint.
        # Construct worker commands for a frozen executable using arguments containing spaces.
        # Command routing must preserve literal values without shell reconstruction.
        script = Path('folder with spaces/native_loader.py')
        with patch.object(sys, 'frozen', True, create=True), patch.object(sys, 'executable', 'trainer path/SkillExpanded.exe'):
            self.assertEqual(worker_command(script, '--dll', 'my folder/runtime.dll'),
                ['trainer path/SkillExpanded.exe', '--worker', 'native_loader', '--dll', 'my folder/runtime.dll'])
        with patch.object(sys, 'frozen', False, create=True):
            self.assertEqual(worker_command(script)[1:3], ['-B', str(script)])

    def test_alternate_steam_library_keeps_exact_build_guard(self):
        # Preserve the exact-build guard when the Steam library path differs.
        # Resolve the game from an alternate installation while validating its supported image.
        # Directory flexibility must never disable executable compatibility checking.
        alternate = ROOT/'work/Alternate Steam Library/nioh.exe'
        with patch.dict(os.environ, {'NIOH_EXE': str(alternate)}):
            spec = importlib.util.spec_from_file_location('alternate_loader', ROOT/'outputs/okatsu-prototype/native_loader.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.assertEqual(module.NIOH, alternate)
            self.assertEqual(module.NIOH_HASH, '0c3508c6b4d0696d84423949df9faccb3f9c6d93833854e1e17a78d66defc389')
