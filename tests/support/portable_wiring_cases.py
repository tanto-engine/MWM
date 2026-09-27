# Offline regression cases for product staging, portable paths and retained developer policy.
# Fixtures isolate game/process effects; these checks do not establish gameplay acceptance.
# Loaded by the existing Engine test entrypoints through Test-Offline.ps1; see CODE_GUIDE.md.
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'runtime'))
from supervisor import session_binary
from process_support import worker_command


class Portability(unittest.TestCase):
    def test_authored_developer_pulse_policy_survives_product_staging(self):
        # Verify that a reviewed developer Ki Pulse policy reaches the packaged Sword data.
        # Stage a copied product tree and inspect the retained policy without creating an EXE.
        # This protects the packaging boundary while keeping private policy out of public preset controls.
        from build_product import stage_product
        policy=dict(schema_version=1,moves={'okatsu.charged_rush':dict(ki_pulse=dict(percent=65,fill_frames=18,hold_frames=35))})
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);project=folder/'sword';stage=folder/'stage'
            shutil.copytree(ROOT.parent/'MWM',project,ignore=shutil.ignore_patterns('.git','.build','dist','runtime','__pycache__'))
            (project/'data/move-policy.json').write_text(json.dumps(policy),encoding='utf8')
            stage_product(project,stage)
            for preset in (project/'data/presets').glob('*.json'):
                self.assertEqual((stage/'data/presets'/preset.name).read_bytes(), preset.read_bytes())
            staged=stage/'data/move-policy.json'
            self.assertTrue(staged.is_file(),'Sword staging dropped authored developer Pulse policy')
            self.assertEqual(json.loads(staged.read_text()),policy)
            manifest=json.loads((stage/'build-manifest.json').read_text())
            self.assertEqual(manifest['files']['data/move-policy.json'],hashlib.sha256(staged.read_bytes()).hexdigest())
            code="import sys,json;sys.path.insert(0,sys.argv[1]);from prepare_session import compiled_move_settings;from engine_config import DEFAULT_PRESET;print(json.dumps(compiled_move_settings(DEFAULT_PRESET,[dict(id='okatsu.charged_rush',flags=0x184C0000)])))"
            result=subprocess.run([sys.executable,'-B','-c',code,str(stage/'runtime')],capture_output=True,text=True,
                env=dict(os.environ,TANTO_MOD_ROOT=str(stage)),timeout=20)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout),[dict(speed=1,percent=65,fill_frames=18,hold_frames=35)])
            policy['moves']['okatsu.charged_rush']['ki_pulse']['percent']=101
            (project/'data/move-policy.json').write_text(json.dumps(policy),encoding='utf8')
            with self.assertRaisesRegex(ValueError,'Ki Pulse percent'):
                stage_product(project,folder/'invalid')
            self.assertFalse((folder/'invalid').exists())

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
        alternate = ROOT/'tests/Alternate Steam Library/nioh.exe'
        with patch.dict(os.environ, {'NIOH_EXE': str(alternate)}):
            spec = importlib.util.spec_from_file_location('alternate_loader', ROOT/'runtime/native_loader.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.assertEqual(module.NIOH, alternate)
            self.assertEqual(module.NIOH_HASH, '0c3508c6b4d0696d84423949df9faccb3f9c6d93833854e1e17a78d66defc389')
