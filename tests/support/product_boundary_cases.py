import hashlib
import json
from pathlib import Path
import sys
import struct
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT.parent/'tanto-recorder/src')]
from build_product import READ_ONLY, stage_product
from recorder import export_capture
from recording_bundle import intake_bundle, session_summary
from encounter_recording import save_annotation
from encounter_recording_cases import state, metadata


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

    def test_summary_and_intake_keep_repeated_evidence_pending(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);take=folder/'take-0001';take.mkdir()
            (folder/'encounter.json').write_text(json.dumps(dict(boss_id='okatsu',recording_id='review',created_at=1)))
            events=[state(.1,counter=1),metadata(),state(.2,counter=2),state(.3,0xC66),metadata(0xC66,1230,t=.31),
                state(.4),metadata(t=.41),{'kind':'end','t':.5}]
            raw='\n'.join(map(json.dumps,events)).encode()
            (take/'events.jsonl').write_bytes(raw)
            first=save_annotation(folder,'Slash',take.name,.1,.3,markers=['unsure'])
            summary=session_summary(folder)
            self.assertEqual(summary['review_status'],'pending')
            self.assertEqual(sum(row['unverified_reentries'] for row in summary['actions']),1)
            self.assertEqual(sum(row['observed_entries'] for row in summary['actions']),2)
            self.assertNotIn(str(folder),json.dumps(summary))
            archive=export_capture(folder,folder/'first.zip')
            target=folder/'intake';report=intake_bundle(archive,target)
            self.assertFalse(report['curated_changes'])
            self.assertEqual(report['review_status'],'pending')
            self.assertFalse(report['takes'][0]['duplicate'])
            self.assertEqual(intake_bundle(archive,target),report)
            save_annotation(folder,'Different move',take.name,.1,.3,label_id=first['label_id'])
            changed=export_capture(folder,folder/'second.zip')
            revised=intake_bundle(changed,target)
            self.assertTrue(revised['takes'][0]['duplicate'])
            self.assertIn('overlapping_labels',{row['kind'] for row in revised['conflicts']})
            self.assertEqual(len(list((target/'captures').glob('*.jsonl'))),1)
            self.assertEqual((take/'events.jsonl').read_bytes(),raw)

    def test_intake_rejects_tampering_and_unlisted_paths_before_staging(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);take=folder/'take-0001';take.mkdir()
            (folder/'encounter.json').write_text(json.dumps(dict(boss_id='okatsu',recording_id='review',created_at=1)))
            (take/'events.jsonl').write_text(json.dumps(state(1)))
            source=export_capture(folder,folder/'original.zip')
            with zipfile.ZipFile(source) as archive:
                members={name:archive.read(name) for name in archive.namelist()}
            for kind in ('tamper','traversal'):
                changed=dict(members)
                changed['take-0001/events.jsonl' if kind=='tamper' else '../outside.json']=b'changed'
                invalid=folder/(kind+'.zip');target=folder/(kind+'-intake')
                with zipfile.ZipFile(invalid,'w') as archive:
                    for name,data in changed.items(): archive.writestr(name,data)
                with self.assertRaises(ValueError): intake_bundle(invalid,target)
                self.assertFalse(target.exists())

    def test_repeated_sequence_retains_native_gates_without_confirming_execution(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);take=folder/'take-0001';take.mkdir()
            (folder/'encounter.json').write_text(json.dumps(dict(boss_id='okatsu',recording_id='sequence')))
            row=bytearray([255]*48)
            struct.pack_into('<5H',row,0,22,*([65535]*4))
            row[10]=0;row[11]=255
            struct.pack_into('<h',row,0x14,0xC66)
            struct.pack_into('<Ihh',row,0x1C,0,-32768,32767)
            a=metadata(transition_entries=[dict(slice_index=0,bytes=row.hex())])
            events=[state(.1),a,state(.2,0xC66),metadata(0xC66,1230,t=.21),
                state(.3),dict(a,t=.31),state(.4,0xC66),metadata(0xC66,1230,t=.41)]
            (take/'events.jsonl').write_text('\n'.join(map(json.dumps,events)))
            summary=session_summary(folder)
            sequence=next(row for row in summary['repeated_sequences'] if len(row['identities'])==2)
            self.assertEqual(sequence['count'],2)
            self.assertEqual(sequence['confidence'],'repeated_order_with_native_links')
            self.assertEqual(sequence['native_links'][0][0]['conditions'][0],22)
            self.assertEqual(sequence['native_links'][0][0]['kind'],'paired_contact')
            self.assertEqual(summary['review_status'],'pending')
