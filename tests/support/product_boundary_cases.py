import hashlib
import json
from pathlib import Path
import sys
import struct
import tempfile
import unittest
import zipfile
import threading
import tkinter as tk
from unittest.mock import patch
import recorder
from recording_hotkey import GlobalHotkey

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT.parent/'tanto-recorder/src')]
from build_product import READ_ONLY, stage_product
from recorder import export_capture
from recording_bundle import intake_bundle, session_summary
from encounter_recording import save_annotation
from encounter_recording_cases import state, metadata


class ProductBoundaryTests(unittest.TestCase):
    def test_local_guide_opens_while_busy_and_does_not_block_stop(self):
        root=tk.Tk();root.withdraw()
        try:
            with tempfile.TemporaryDirectory() as td:
                settings=Path(td)/'settings.json'
                app=recorder.Recorder(root,enable_hotkey=False,settings_path=settings)
                app.busy=lambda:True
                app.backdrop.on_guide()
                self.assertIsNotNone(app.guide);self.assertTrue(app.guide.winfo_exists())
                self.assertFalse(app.guide.grab_current())
                app.toggle();self.assertTrue(app.stop.is_set())
                canvas=app.guide.winfo_children()[0]
                next(w for w in canvas.winfo_children() if w.winfo_class()=='TButton').invoke()
                self.assertTrue(json.loads(settings.read_text())['tutorial_seen'])
                self.assertIsNone(app.guide);app.busy=lambda:False;app.close()
        finally:
            try:root.destroy()
            except tk.TclError:pass

    def test_windows_hotkey_messages_start_and_stop_capture_without_game_input(self):
        import ctypes as C
        from ctypes import wintypes as W
        import time
        root=tk.Tk();root.withdraw();entered=threading.Event();stopped=threading.Event()
        def capture(boss,folder,**options):
            entered.set()
            if options['stop_event'].wait(3): stopped.set()
        def until(predicate):
            deadline=time.monotonic()+2
            while not predicate() and time.monotonic()<deadline:
                root.update();time.sleep(.01)
            self.assertTrue(predicate())
        try:
            with tempfile.TemporaryDirectory() as td, patch.object(recorder,'record_encounter',side_effect=capture) as backend, \
                 patch.object(recorder,'downloads_dir',return_value=Path(td)/'Redirected Downloads'):
                settings=Path(td)/'settings.json';settings.write_text('{"hotkey":"Ctrl+Shift+R"}')
                app=recorder.Recorder(root,settings_path=settings);app.boss.set('Onryoki')
                until(lambda:'starts / stops' in app.hotkey_status.get())
                api=C.WinDLL('user32',use_last_error=True)
                api.PostThreadMessageW.argtypes=[W.DWORD,W.UINT,W.WPARAM,W.LPARAM];api.PostThreadMessageW.restype=W.BOOL
                def message():
                    self.assertTrue(api.PostThreadMessageW(app.hotkey.thread.native_id,0x0312,1,0))
                message();until(entered.is_set)
                self.assertEqual(app.folder.parent,Path(td)/'Redirected Downloads/Tanto Recordings')
                message();until(stopped.is_set);until(lambda:not app.busy())
                self.assertEqual(backend.call_count,1)
                app.close();self.assertFalse(app.hotkey)
        finally:
            if 'app' in locals():
                app.stop.set()
                if app.hotkey: app.hotkey.close()
            try: root.destroy()
            except tk.TclError: pass

    def test_description_editor_saves_a_span_and_retains_revision_history(self):
        root=tk.Tk();root.withdraw()
        try:
            with tempfile.TemporaryDirectory() as td:
                folder=Path(td);take=folder/'take-0001';take.mkdir()
                (folder/'encounter.json').write_text(json.dumps(dict(boss_id='okatsu',recording_id='editor')))
                (take/'events.jsonl').write_text('{"kind":"end","t":3.5}\n')
                app=recorder.Recorder(root,enable_hotkey=False,settings_path=folder/'settings.json');app.folder=folder
                app.describe()
                for description in ('Jump then slash','Jump then two slashes'):
                    editor=app.description
                    editor.delete('1.0','end');editor.insert('1.0',description)
                    self.assertTrue(app.save_description())
                    label=recorder.load_annotations(folder)[0]
                    self.assertEqual((label['start_t'],label['end_t']),(0,3.5))
                    self.assertEqual(label['label'],description)
                    if label['revision']==1:
                        app.labels.selection_set(label['label_id']);app.edit_selected()
                self.assertEqual(label['revision'],2);app.close()
        finally:
            try: root.destroy()
            except tk.TclError: pass

    def test_description_is_editable_before_samples_and_survives_restart(self):
        with tempfile.TemporaryDirectory() as td:
            settings=Path(td)/'new/settings.json'
            for attempt in range(2):
                root=tk.Tk();root.withdraw();app=recorder.Recorder(root,False,settings)
                try:
                    app.describe()
                    if not attempt:
                        app.boss.set('Custom enemy');app.description.insert('1.0','Jump, then two cuts')
                        self.assertFalse(app.save_description())
                    else:
                        self.assertEqual(app.boss.get(),'Custom enemy')
                        self.assertEqual(app.description.get('1.0','end-1c'),'Jump, then two cuts')
                finally:app.close()

    def test_last_session_and_unsaved_revision_are_restored(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td)/'session';folder.mkdir();settings=Path(td)/'settings.json'
            take=folder/'take-0001';take.mkdir()
            (folder/'encounter.json').write_text(json.dumps(dict(boss_id='okatsu',boss_name='Okatsu')))
            (take/'events.jsonl').write_text('{"kind":"end","t":3.5}\n')
            root=tk.Tk();root.withdraw();app=recorder.Recorder(root,False,settings)
            app.load_session(folder);app.description.insert('1.0','First slash');self.assertTrue(app.save_description())
            key=app.labels.get_children()[0];app.labels.selection_set(key);app.edit_selected()
            app.description.insert('end',' and leap');app.close()
            root=tk.Tk();root.withdraw();app=recorder.Recorder(root,False,settings)
            try:
                self.assertEqual(app.folder,folder)
                self.assertEqual(app.description.get('1.0','end-1c'),'First slash and leap')
                self.assertTrue(app.save_description());labels=recorder.load_annotations(folder)
                self.assertEqual(len(labels),1);self.assertEqual(labels[0]['revision'],2)
                self.assertEqual(labels[0]['label'],'First slash and leap')
            finally:app.close()

    def test_disk_failure_keeps_description_and_prevents_close(self):
        with tempfile.TemporaryDirectory() as td:
            root=tk.Tk();root.withdraw();app=recorder.Recorder(root,False,Path(td)/'settings.json')
            app.description.insert('1.0','Keep this note')
            with patch.object(recorder,'atomic_json',side_effect=OSError('Disk full')):
                self.assertFalse(app.save_description());app.close()
                self.assertFalse(app.closing);self.assertIn('Disk full',app.note_status.get())
                self.assertEqual(app.description.get('1.0','end-1c'),'Keep this note')
            app.close()

    def test_capture_resume_preserves_takes_and_plays_confirmed_cues(self):
        with tempfile.TemporaryDirectory() as td:
            root=tk.Tk();root.withdraw();settings=Path(td)/'settings.json'
            def capture(boss,folder,**options):
                index=len(list(folder.glob('take-*')))+1;take=folder/f'take-{index:04d}';take.mkdir()
                (take/'events.jsonl').write_text('{"kind":"end","t":3.5}\n')
                options['status_callback'](dict(state='recording',detail='test'))
                options['stop_event'].wait(2)
                options['status_callback'](dict(state='stopped',detail='saved'))
            with patch.object(recorder,'record_encounter',side_effect=capture),patch.object(recorder,'downloads_dir',return_value=Path(td)),patch.object(recorder.Recorder,'cue') as cue:
                app=recorder.Recorder(root,False,settings);app.boss.set('Onryoki')
                for index in range(2):
                    app.toggle();self.assertTrue((app.folder/'encounter.json').exists())
                    app.toggle();app.thread.join(3)
                    root.after_cancel(app.after_id);app.poll()
                    app.description.insert('1.0',f'Sequence {index+1}')
                    self.assertTrue(app.save_description())
                self.assertEqual([x['take'] for x in recorder.load_annotations(app.folder)],['take-0001','take-0002'])
                self.assertEqual([x.args[0] for x in cue.call_args_list],['start','stop','start','stop'])
                app.close()

    def test_queued_completion_cannot_overwrite_a_new_session(self):
        with tempfile.TemporaryDirectory() as td:
            root=tk.Tk();root.withdraw();app=recorder.Recorder(root,False,Path(td)/'settings.json')
            previous=Path(td)/'old';previous.mkdir();app.folder=previous
            app.events.put(('capture_status',(previous,dict(state='recording',detail='old')),None))
            app.events.put(('capture_finished',previous,None))
            app.new_session();root.after_cancel(app.after_id);app.poll()
            self.assertEqual(app.headline.get(),'New session');self.assertIsNone(app.folder);app.close()

    def test_boss_menu_names_do_not_invent_detection_signatures(self):
        self.assertGreaterEqual(len(recorder.BOSSES),40)
        key,name=recorder.boss_identity('Onryoki')
        self.assertEqual(name,'Onryoki');self.assertNotIn(key,recorder.DEFAULT_SIGNATURES)
        self.assertEqual(set(recorder.DEFAULT_SIGNATURES),{'okatsu','jin_hayabusa','maria'})

    def test_intake_reports_raw_context_disagreeing_with_submission(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);take=folder/'take-0001';take.mkdir()
            (folder/'encounter.json').write_text(json.dumps(dict(boss_id='okatsu',recording_id='context',created_at=1)))
            (take/'events.jsonl').write_text(json.dumps(dict(kind='session',encounter_context=dict(boss_id='maria'))))
            archive=export_capture(folder,folder/'share.zip');report=intake_bundle(archive,folder/'intake')
            self.assertIn('capture_context',{item['kind'] for item in report['conflicts']})

    def test_intake_rejects_malformed_manifest_shapes_before_staging(self):
        for manifest in ([],dict(kind='tanto_recording',schema_version=1,boss_id='okatsu',files=[{}])):
            with tempfile.TemporaryDirectory() as td:
                folder=Path(td);archive_path=folder/'malformed.zip'
                with zipfile.ZipFile(archive_path,'w') as archive:
                    archive.writestr('manifest.json',json.dumps(manifest))
                with self.assertRaises(ValueError): intake_bundle(archive_path,folder/'intake')
                self.assertFalse((folder/'intake').exists())

    def test_recorder_requires_name_and_serializes_hotkey_stop_and_close(self):
        root=tk.Tk();root.withdraw();entered=threading.Event();finish=threading.Event()
        def capture(boss,folder,**options):
            self.assertTrue(boss.startswith('encounter_'))
            self.assertEqual(options['boss_name'],'Onryoki')
            entered.set();finish.wait(3)
        try:
            with tempfile.TemporaryDirectory() as td, patch.object(recorder,'record_encounter',side_effect=capture) as backend:
                app=recorder.Recorder(root,enable_hotkey=False,settings_path=Path(td)/'settings.json')
                app.toggle();backend.assert_not_called()
                app.boss.set('  Onryoki  ');app.toggle();self.assertTrue(entered.wait(1))
                worker=app.thread;app.toggle();app.toggle()
                self.assertIs(app.thread,worker);self.assertTrue(app.stop.is_set());self.assertEqual(backend.call_count,1)
                app.close();self.assertTrue(root.winfo_exists())
                finish.set();worker.join(2);self.assertFalse(worker.is_alive())
                app.close()
        finally:
            finish.set()
            try: root.destroy()
            except tk.TclError: pass

    def test_recorder_layout_resizes_at_multiple_font_scales(self):
        for scaling in (1.33,2.0,2.67):
            root=tk.Tk();root.attributes('-alpha',0);root.tk.call('tk','scaling',scaling)
            errors=[];root.report_callback_exception=lambda kind,error,trace:errors.append(str(error))
            try:
                with tempfile.TemporaryDirectory() as td:
                    app=recorder.Recorder(root,enable_hotkey=False,settings_path=Path(td)/'settings.json')
                    for width,height in ((680,650),(960,740),(1400,950)):
                        root.geometry(f'{width}x{height}');root.update()
                        self.assertFalse(errors)
                        self.assertEqual(app.backdrop.picture.width(),app.backdrop.winfo_width())
                        self.assertEqual(app.backdrop.picture.height(),app.backdrop.winfo_height())
                        self.assertEqual(app.help_label.photo.get(0,0),app.backdrop.crop(app.help_label).getpixel((0,0)))
                        for widget in (app.selector,app.primary,app.help_label,app.labels,app.description,app.save_button,*app.idle_buttons):
                            self.assertGreater(widget.winfo_width(),20)
                            self.assertGreaterEqual(widget.winfo_rootx(),root.winfo_rootx())
                            self.assertLessEqual(widget.winfo_rootx()+widget.winfo_width(),root.winfo_rootx()+root.winfo_width())
                            self.assertLessEqual(widget.winfo_rooty()+widget.winfo_height(),root.winfo_rooty()+root.winfo_height())
                    app.close()
            finally:
                try: root.destroy()
                except tk.TclError: pass

    def test_export_is_background_work_and_close_waits_for_it(self):
        root=tk.Tk();root.withdraw();entered=threading.Event();finish=threading.Event()
        def export(folder,path):
            entered.set();finish.wait(3);return path
        try:
            with tempfile.TemporaryDirectory() as td, patch.object(recorder,'export_capture',side_effect=export):
                app=recorder.Recorder(root,enable_hotkey=False,settings_path=Path(td)/'settings.json');app.folder=Path(td)
                app.export();self.assertTrue(entered.wait(1));self.assertEqual(app.operation,'export')
                worker=app.thread;app.toggle();self.assertIs(app.thread,worker)
                root.update();app.close();self.assertTrue(root.winfo_exists())
                finish.set();worker.join(2);app.close()
        finally:
            finish.set()
            try: root.destroy()
            except tk.TclError: pass

    def test_global_hotkey_registration_conflict_and_release_without_key_input(self):
        events=[];first=GlobalHotkey('Ctrl+Shift+R',lambda kind,value:events.append((kind,value)))
        # Register on separate threads; no key presses, hooks or game access.
        try:
            import time
            deadline=time.monotonic()+2
            while not events and time.monotonic()<deadline: time.sleep(.01)
            self.assertEqual(events[0][0],'hotkey_ready')
            conflict=[];second=GlobalHotkey('Ctrl+Shift+R',lambda kind,value:conflict.append((kind,value)))
            second.thread.join(2);second.close()
            self.assertEqual(conflict[0][0],'hotkey_error')
        finally: first.close()
        released=[];third=GlobalHotkey('Ctrl+Shift+R',lambda kind,value:released.append((kind,value)))
        try:
            deadline=time.monotonic()+2
            while not released and time.monotonic()<deadline: time.sleep(.01)
            self.assertEqual(released[0][0],'hotkey_ready')
        finally: third.close()

    def test_unknown_boss_name_survives_export_and_intake_without_verification(self):
        boss,name=recorder.boss_identity('大蝦蟇')
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);take=folder/'take-0001';take.mkdir()
            (folder/'encounter.json').write_text(json.dumps(dict(boss_id=boss,boss_name=name,recording_id='unknown',created_at=1)))
            (take/'events.jsonl').write_text(json.dumps(state(.1,role='unassigned')))
            target=export_capture(folder,folder/'share.zip');report=intake_bundle(target,folder/'intake')
            self.assertEqual(report['boss_name'],name);self.assertEqual(report['review_status'],'pending')
            with zipfile.ZipFile(target) as archive:
                summary=json.loads(archive.read('Summary.json'))
                self.assertTrue(all(row['confidence']=='identity_unverified' for row in summary['actions']))

    def test_failed_export_leaves_no_shareable_partial_archive(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);take=folder/'take-0001';take.mkdir()
            (folder/'encounter.json').write_text(json.dumps(dict(boss_id='okatsu',recording_id='failure',created_at=1)))
            (take/'events.jsonl').write_text('{"kind":"end","t":1}\n')
            target=folder/'share.zip'
            with patch('zipfile.ZipFile.writestr',side_effect=OSError('Disk full')):
                with self.assertRaises(OSError): export_capture(folder,target)
            self.assertFalse(target.exists())

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
