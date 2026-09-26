import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT.parent/'tanto-recorder/src')]
from build_product import READ_ONLY, stage_product
from recorder import export_capture


class ProductBoundaryTests(unittest.TestCase):
    def test_recorder_package_contains_only_read_only_engine_modules(self):
        # A recorder release must never depend on gameplay policy, hooks or catalogue workbooks.
        # Exercise the same staging operation used by the binary build.
        # Raw recordings and developer fixtures remain outside the user package.
        with tempfile.TemporaryDirectory() as folder:
            destination=Path(folder)/'stage'
            stage_product(ROOT.parent/'tanto-recorder',destination)
            self.assertEqual({p.stem for p in (destination/'runtime').glob('*.py')},set(READ_ONLY))
            self.assertEqual({p.name for p in (destination/'data').iterdir()},{'bosses.json'})
            self.assertFalse(list(destination.rglob('*.dll')))
            self.assertFalse((destination/'captures').exists())

    def test_sword_package_excludes_capture_and_editor_tools(self):
        # Verify the micro-runtime has preparation primitives without recording/editor APIs.
        # Parse the staged source without attaching to Nioh or executing native code.
        # Product resources and runtime libraries must be self-contained.
        with tempfile.TemporaryDirectory() as folder:
            destination=Path(folder)/'stage'
            stage_product(ROOT.parent/'tanto-sword-mod',destination)
            self.assertNotIn('def record(', (destination/'runtime/boss_probe.py').read_text())
            self.assertNotIn('def save_catalogue(', (destination/'runtime/catalogue.py').read_text())
            self.assertTrue((destination/'runtime/native/build/nioh_skill_runtime.dll').is_file())
            self.assertFalse(list(destination.rglob('*.cpp')))
            self.assertFalse(list(destination.rglob('*.xlsx')))

    def test_contributor_export_preserves_evidence_and_excludes_local_logs(self):
        # Export raw data, hash provenance and readable descriptions from one completed session.
        # Unrelated local files must never enter the shareable archive.
        # Spreadsheet formula-like descriptions remain literal text.
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);take=folder/'take-0001';take.mkdir()
            raw=b'{"kind":"end","t":3}\n';(take/'events.jsonl').write_bytes(raw)
            (folder/'encounter.json').write_text(json.dumps(dict(boss_id='okatsu',recording_id='test',created_at=1)))
            (folder/'labels.jsonl').write_text(json.dumps(dict(label='=bad()',take='take-0001',last_recorded_t=3))+'\n')
            (folder/'private.log').write_text('not exported')
            destination=export_capture(folder,folder/'share.zip')
            with zipfile.ZipFile(destination) as archive:
                self.assertNotIn('private.log',archive.namelist())
                self.assertEqual(archive.read('take-0001/events.jsonl'),raw)
                manifest=json.loads(archive.read('manifest.json'))
                self.assertEqual(manifest['files'][0]['sha256'],hashlib.sha256(raw).hexdigest())
                self.assertIn("'=bad()",archive.read('Descriptions.csv').decode('utf-8-sig'))
