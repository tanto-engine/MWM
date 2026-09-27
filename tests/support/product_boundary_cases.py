# Offline regression cases for Recorder workflow, read-only packaging, export/intake and release gates.
# Fixtures isolate game/process effects; these checks do not establish gameplay acceptance.
# Loaded by the existing Engine test entrypoints through Test-Offline.ps1; see CODE_GUIDE.md.
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
import build_product
from recorder import export_capture
from recording_bundle import intake_bundle, session_summary, export_sessions
from recording_hotkey import parse_hotkey
from encounter_recording import save_annotation
from encounter_recording_cases import state, metadata


class ProductBoundaryTests(unittest.TestCase):
    def test_multi_session_export_and_intake_preserve_bosses_takes_and_revisions(self):
        # Export two same-boss sessions and another boss, including repeated folder names.
        # Check inner ZIP histories, collection intake, deduplication and conflicting boss attribution.
        # The collection must preserve all session identities without rewriting original labels or raw evidence.
        with tempfile.TemporaryDirectory() as td:
            base=Path(td);folders=[];originals={}
            for index,boss in enumerate(('okatsu','okatsu','maria')):
                folder=base/str(index)/'same-name';take=folder/'take-0001';take.mkdir(parents=True);folders.append(folder)
                (folder/'encounter.json').write_text(json.dumps(dict(boss_id=boss,boss_name=boss.title(),recording_id=str(index),created_at=1)))
                (take/'events.jsonl').write_text(json.dumps(state(2)))
                label=save_annotation(folder,'First description',take.name,0,2)
                save_annotation(folder,'Revised description',take.name,0,2,label_id=label['label_id'])
                originals[folder]=(folder/'labels.jsonl').read_bytes()
            path=export_sessions(folders,base/'tanto-zips/share.zip')
            report=intake_bundle(path,base/'intake')
            self.assertEqual([item['boss_id'] for item in report['sessions']],['okatsu','okatsu','maria'])
            self.assertTrue(all(item['annotations'][0]['revision']==2 for item in report['sessions']))
            self.assertEqual(intake_bundle(path,base/'intake'),report)
            self.assertEqual(len(list((base/'intake/captures').glob('*.jsonl'))),1)
            self.assertIn('boss_identity',{c['kind'] for c in report['sessions'][2]['conflicts']})
            with zipfile.ZipFile(path) as outer:
                self.assertEqual(len(outer.namelist()),4)
                import io
                for index,folder in enumerate(folders,1):
                    with zipfile.ZipFile(io.BytesIO(outer.read(f'session-{index:04d}.zip'))) as inner:
                        self.assertEqual(inner.read('labels.jsonl'),originals[folder])
                    self.assertEqual((folder/'labels.jsonl').read_bytes(),originals[folder])

    def test_collection_rejects_a_bad_later_session_before_saving_any_evidence(self):
        # Put a valid session before a malformed one in a collection.
        # Verify intake rejects the entire collection before creating its evidence destination.
        # Also reject a non-session export selection without leaving a shareable partial ZIP.
        with tempfile.TemporaryDirectory() as td:
            base=Path(td);folder=base/'session';take=folder/'take-0001';take.mkdir(parents=True)
            (folder/'encounter.json').write_text(json.dumps(dict(boss_id='okatsu',recording_id='test',created_at=1)))
            (take/'events.jsonl').write_text(json.dumps(state(2)))
            good=export_capture(folder,base/'good.zip').read_bytes()
            import io
            malformed=io.BytesIO()
            with zipfile.ZipFile(malformed,'w') as archive:archive.writestr('manifest.json','{}')
            archive_path=base/'bad-collection.zip';entries=[]
            with zipfile.ZipFile(archive_path,'w') as archive:
                for index,data in enumerate((good,malformed.getvalue()),1):
                    name=f'session-{index:04d}.zip';archive.writestr(name,data)
                    entries.append(dict(path=name,size=len(data),sha256=hashlib.sha256(data).hexdigest()))
                archive.writestr('manifest.json',json.dumps(dict(kind='tanto_recording_collection',schema_version=1,sessions=entries)))
            with self.assertRaises(ValueError):intake_bundle(archive_path,base/'intake')
            self.assertFalse((base/'intake').exists())
            with self.assertRaises(ValueError):export_sessions([folder,base],base/'failed.zip')
            self.assertFalse((base/'failed.zip').exists())

    def test_existing_recording_library_and_custom_binding_survive_upgrade(self):
        # Reopen an existing recording library after restarting the UI with saved preferences.
        # Restore its session and custom shortcut, then create another encounter in the same library.
        # Compare old raw bytes afterward so compatibility cannot hide accidental replacement of recordings.
        with tempfile.TemporaryDirectory() as td:
            base=Path(td);library=base/'Tanto Recordings';session=library/'old';take=session/'take-0001';take.mkdir(parents=True)
            (session/'encounter.json').write_text(json.dumps(dict(boss_id='okatsu',boss_name='Okatsu',recording_id='old',created_at=1)))
            raw=b'{"kind":"end","t":2}\n';(take/'events.jsonl').write_bytes(raw)
            settings=base/'settings.json'
            root=tk.Tk();root.withdraw();app=recorder.Recorder(root,False,settings)
            try:
                self.assertTrue(app.set_recordings(library));app.load_session(session)
                app.key.set('Ctrl+Alt+K');app.configure_hotkey();app.close()
                root=tk.Tk();root.withdraw();app=recorder.Recorder(root,False,settings)
                self.assertEqual(app.recordings,library);self.assertEqual(app.folder,session)
                self.assertEqual(app.key.get(),'Ctrl+Alt+K')
                app.new_session();app.boss.set('Maria')
                with patch.object(recorder,'record_encounter') as backend:
                    app.start();app.thread.join(2)
                self.assertEqual(app.folder.parent,library);self.assertNotEqual(app.folder,session)
                self.assertEqual((take/'events.jsonl').read_bytes(),raw)
                self.assertEqual(backend.call_count,1)
            finally:app.close()

    def test_custom_hotkey_capture_cancel_and_reserved_shortcuts(self):
        # Check configurable keyboard shortcuts without injecting any physical key presses.
        # Exercise parsing, reserved combinations, Escape cancellation and an accepted synthetic Tk key event.
        # Only an accepted binding may replace the saved shortcut.
        from types import SimpleNamespace
        self.assertEqual(parse_hotkey('Ctrl+Alt+K'),(3,ord('K')))
        for key in ('K','F1','F12','Ctrl+S','Alt+F4','Ctrl+Ctrl+K','Ctrl+Shift'):
            with self.assertRaises(ValueError):parse_hotkey(key)
        with tempfile.TemporaryDirectory() as td:
            root=tk.Tk();root.withdraw();app=recorder.Recorder(root,False,Path(td)/'settings.json')
            try:
                app.begin_binding();app.capture_binding(SimpleNamespace(keysym='Escape'))
                self.assertEqual(app.key.get(),'F8');self.assertIsNone(app.binding)
                app.begin_binding();app.capture_binding(SimpleNamespace(keysym='k',state=4|8))
                self.assertEqual(app.key.get(),'Ctrl+Alt+K');self.assertIsNone(app.binding)
                self.assertEqual(json.loads(app.settings_path.read_text())['hotkey'],'Ctrl+Alt+K')
            finally:app.close()

    def test_export_picker_cancellation_is_idle_and_can_export_without_open_session(self):
        # Check export selection independently of whichever session is currently open.
        # Mock an empty picker result, then selected folders and a redirected Downloads location.
        # Cancellation stays idle; selected sessions are sent to the collection exporter under tanto-zips.
        with tempfile.TemporaryDirectory() as td:
            root=tk.Tk();root.withdraw();app=recorder.Recorder(root,False,Path(td)/'settings.json')
            try:
                with patch.object(recorder,'choose_recording_folders',return_value=[]):app.export()
                self.assertFalse(app.busy());self.assertIsNone(app.operation)
                with patch.object(recorder,'choose_recording_folders',return_value=[Path(td)]), \
                     patch.object(recorder,'downloads_dir',return_value=Path(td)/'Downloads'), \
                     patch.object(recorder,'export_sessions',return_value=Path(td)/'share.zip') as export:
                    app.export();app.thread.join(2)
                    self.assertEqual(export.call_args.args[0],[Path(td)])
                    self.assertEqual(export.call_args.args[1].parent,Path(td)/'Downloads/tanto-zips')
            finally:app.close()

    def test_exe_release_gate_rejects_unversioned_dirty_unpinned_and_reused_builds(self):
        # Exercise release rejection without invoking a compiler or creating an EXE.
        # Vary version syntax, dirty source, Engine pin and an existing version directory.
        # Only traceable clean inputs with an unused version may reach packaging.
        with tempfile.TemporaryDirectory() as td:
            base=Path(td);engine=base/'tanto-engine';engine.mkdir()
            product=base/'tanto-recorder';product.mkdir();(base/'SKM').mkdir()
            spec=dict(kind='recorder',name='TantoRecorder',version='0.2.0-alpha.1',engine_commit='a'*40)
            (product/'CHANGELOG.md').write_text('## 0.2.0-alpha.1\n\nOffline only.\n')
            def write():
                # Save the current candidate manifest inside the disposable release fixture.
                # Each case changes one input and reuses this helper to make that change visible to the builder.
                # No real product manifest or published release is modified.
                (product/'product.json').write_text(json.dumps(spec))
            write()
            with patch.object(build_product,'ROOT',engine), patch.object(build_product,'source_state',return_value=dict(commit='a'*40,dirty=False)) as state, \
                 patch.object(build_product.subprocess,'check_output',return_value=''):
                self.assertEqual(build_product.release_inputs(product)[0],spec)
                for version in ('','latest','0.2','../../escape','0.2.0-alpha.0'):
                    spec['version']=version;write()
                    with self.assertRaises(ValueError):build_product.release_inputs(product)
                spec['version']='0.2.0-alpha.1';write()
                state.return_value=dict(commit='a'*40,dirty=True)
                with self.assertRaises(ValueError):build_product.release_inputs(product)
                state.return_value=dict(commit='b'*40,dirty=False)
                with self.assertRaises(ValueError):build_product.release_inputs(product)
                state.return_value=dict(commit='a'*40,dirty=False)
                (product/'dist'/spec['version']).mkdir(parents=True)
                with self.assertRaises(ValueError):build_product.release_inputs(product)

    def test_local_guide_opens_while_busy_and_does_not_block_stop(self):
        # Check that the tutorial remains an inline page while recording is busy.
        # Assert it shares the main window, takes no modal grab and leaves Stop operational.
        # Completing it persists the guide preference, and reopening still selects the Guide tab.
        root=tk.Tk();root.withdraw()
        try:
            with tempfile.TemporaryDirectory() as td:
                settings=Path(td)/'settings.json'
                app=recorder.Recorder(root,enable_hotkey=False,settings_path=settings)
                app.busy=lambda: (
                    # Pretend a Recorder worker is busy for the inline-guide lifecycle check.
                    # This tests whether opening help still allows a cooperative Stop request.
                    # No actual capture thread or game process is needed for this branch.
                    True
                )
                app.backdrop.on_guide()
                self.assertIsNotNone(app.guide);self.assertTrue(app.guide.winfo_exists())
                self.assertFalse(app.guide.grab_current())
                app.toggle();self.assertTrue(app.stop.is_set())
                self.assertIs(app.guide.winfo_toplevel(),root)
                self.assertNotIsInstance(app.guide,tk.Toplevel)
                app.guide.done.invoke()
                self.assertTrue(json.loads(settings.read_text())['tutorial_seen'])
                self.assertEqual(app.current_tab,'Record');app.show_guide();self.assertEqual(app.current_tab,'Guide');app.busy=lambda: (
                    # Return the fixture to an idle state before normal UI cleanup.
                    # The close path can now destroy the test window without waiting for a nonexistent worker.
                    # This replaces only the test instance's busy query.
                    False
                );app.close()
        finally:
            try:root.destroy()
            except tk.TclError:pass

    def test_windows_hotkey_messages_start_and_stop_capture_without_game_input(self):
        # Exercise real Windows hotkey-message delivery with a fake capture backend.
        # Post messages to Recorder's listener thread rather than injecting keys into any application.
        # Verify one start, one cooperative stop and the resolved Downloads recording location.
        import ctypes as C
        from ctypes import wintypes as W
        import time
        root=tk.Tk();root.withdraw();entered=threading.Event();stopped=threading.Event()
        def capture(boss,folder,**options):
            # Stand in for a running recording worker using synchronization events.
            # Signal entry, then wait for Recorder's production stop event.
            # No process memory is opened, so the test can verify lifecycle behavior without Nioh.
            entered.set()
            if options['stop_event'].wait(3): stopped.set()
        def until(predicate):
            # Pump Tk until the expected asynchronous event occurs or a short deadline expires.
            # Bound the wait so a broken worker or hotkey path fails the suite instead of hanging.
            # Assert the condition after pumping rather than mistaking elapsed time for successful delivery.
            deadline=time.monotonic()+2
            while not predicate() and time.monotonic()<deadline:
                root.update();time.sleep(.01)
            self.assertTrue(predicate())
        try:
            with tempfile.TemporaryDirectory() as td, patch.object(recorder,'record_encounter',side_effect=capture) as backend, \
                 patch.object(recorder,'downloads_dir',return_value=Path(td)/'Redirected Downloads'):
                settings=Path(td)/'settings.json';settings.write_text('{"hotkey":"Ctrl+Shift+R"}')
                app=recorder.Recorder(root,settings_path=settings);app.boss.set('Onryoki')
                until(lambda: (
                    # Wait for the UI to consume the listener's registration-ready message.
                    # Inspect the status produced through the real queue and Tk poll path.
                    # Readiness here concerns Windows registration, not live-game shortcut acceptance.
                    'starts / stops' in app.hotkey_status.get()
                ))
                api=C.WinDLL('user32',use_last_error=True)
                api.PostThreadMessageW.argtypes=[W.DWORD,W.UINT,W.WPARAM,W.LPARAM];api.PostThreadMessageW.restype=W.BOOL
                def message():
                    # Post WM_HOTKEY directly to the registered listener thread.
                    # Use its current thread ID and the registration's hotkey identifier.
                    # This tests message routing without pressing keys or affecting the focused game/application.
                    self.assertTrue(api.PostThreadMessageW(app.hotkey.thread.native_id,0x0312,1,0))
                message();until(entered.is_set)
                self.assertEqual(app.folder.parent,Path(td)/'Redirected Downloads/Tanto Recordings')
                message();until(stopped.is_set);until(lambda: (
                    # Wait until the test recording worker has actually exited.
                    # The Stop request alone is insufficient because a worker may still be flushing.
                    # Only an idle worker allows the test to complete its normal close path.
                    not app.busy()
                ))
                self.assertEqual(backend.call_count,1)
                app.close();self.assertFalse(app.hotkey)
        finally:
            if 'app' in locals():
                app.stop.set()
                if app.hotkey: app.hotkey.close()
            try: root.destroy()
            except tk.TclError: pass

    def test_description_editor_saves_a_span_and_retains_revision_history(self):
        # Save a sequence description and then edit it through the same UI path.
        # Read back its take interval, wording and revision number from disk.
        # The correction must remain a new revision of the original annotation, not a replacement raw take.
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
        # Allow a contributor to draft notes before a recording exists.
        # Close and reopen Recorder with the same settings file and compare the unfinished text/name.
        # Saving a draft must not falsely attach it to a nonexistent sequence.
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
        # Restore both the last session and an unfinished edit of one saved description.
        # Restart the UI, complete the correction and read the annotation history.
        # The edit must keep its original label identity while increasing its revision once.
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
        # Simulate a failed atomic settings write while the editor contains text.
        # Attempt to save and close, then check that the window remains open with the error visible.
        # An I/O failure must not silently discard a contributor's unfinished description.
        with tempfile.TemporaryDirectory() as td:
            root=tk.Tk();root.withdraw();app=recorder.Recorder(root,False,Path(td)/'settings.json')
            app.description.insert('1.0','Keep this note')
            with patch.object(recorder,'atomic_json',side_effect=OSError('Disk full')):
                self.assertFalse(app.save_description());app.close()
                self.assertFalse(app.closing);self.assertIn('Disk full',app.note_status.get())
                self.assertEqual(app.description.get('1.0','end-1c'),'Keep this note')
            app.close()

    def test_capture_resume_preserves_takes_and_plays_confirmed_cues(self):
        # Stop and resume one session while preserving its earlier takes.
        # Use a fake backend that announces actual sampling, then inspect the start/stop cue sequence.
        # Discovery alone must not sound like recording has started, and resumed takes must remain separate.
        with tempfile.TemporaryDirectory() as td:
            root=tk.Tk();root.withdraw();settings=Path(td)/'settings.json'
            def capture(boss,folder,**options):
                # Create one new numbered fixture take for each simulated recording interval.
                # Publish a recording status and wait for the same stop event used by the real worker.
                # This isolates resume/cue behavior from game discovery and physical audio acceptance.
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
        # Leave old progress/completion messages queued while switching to a new session.
        # Run the UI poll against those stale folder identities.
        # The new encounter's status must remain intact rather than inheriting the old worker's completion.
        with tempfile.TemporaryDirectory() as td:
            root=tk.Tk();root.withdraw();app=recorder.Recorder(root,False,Path(td)/'settings.json')
            previous=Path(td)/'old';previous.mkdir();app.folder=previous
            app.events.put(('capture_status',(previous,dict(state='recording',detail='old')),None))
            app.events.put(('capture_finished',previous,None))
            app.new_session();root.after_cancel(app.after_id);app.poll()
            self.assertEqual(app.headline.get(),'New session');self.assertIsNone(app.folder);app.close()

    def test_boss_menu_names_do_not_invent_detection_signatures(self):
        # Check that the broad boss-name menu remains separate from identity verification.
        # Compare named encounters with the small set of configured action/motion fingerprints.
        # A familiar boss label must not make an unverified recording appear identified.
        self.assertGreaterEqual(len(recorder.BOSSES),40)
        key,name=recorder.boss_identity('Onryoki')
        self.assertEqual(name,'Onryoki');self.assertNotIn(key,recorder.DEFAULT_SIGNATURES)
        self.assertEqual(set(recorder.DEFAULT_SIGNATURES),{'okatsu','jin_hayabusa','maria'})

    def test_intake_reports_raw_context_disagreeing_with_submission(self):
        # Submit a session whose outer boss name conflicts with its raw encounter context.
        # Process it through ordinary export and intake.
        # The report must retain a conflict for human review instead of silently relabeling the raw observation.
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);take=folder/'take-0001';take.mkdir()
            (folder/'encounter.json').write_text(json.dumps(dict(boss_id='okatsu',recording_id='context',created_at=1)))
            (take/'events.jsonl').write_text(json.dumps(dict(kind='session',encounter_context=dict(boss_id='maria'))))
            archive=export_capture(folder,folder/'share.zip');report=intake_bundle(archive,folder/'intake')
            self.assertIn('capture_context',{item['kind'] for item in report['conflicts']})

    def test_intake_rejects_malformed_manifest_shapes_before_staging(self):
        # Try malformed top-level manifests and incomplete file entries.
        # Run the real intake validator against disposable ZIPs.
        # Validation must fail before creating the review destination or staging evidence.
        for manifest in ([],dict(kind='tanto_recording',schema_version=1,boss_id='okatsu',files=[{}])):
            with tempfile.TemporaryDirectory() as td:
                folder=Path(td);archive_path=folder/'malformed.zip'
                with zipfile.ZipFile(archive_path,'w') as archive:
                    archive.writestr('manifest.json',json.dumps(manifest))
                with self.assertRaises(ValueError): intake_bundle(archive_path,folder/'intake')
                self.assertFalse((folder/'intake').exists())

    def test_recorder_requires_name_and_serializes_hotkey_stop_and_close(self):
        # Reject an unnamed start, then exercise repeated Stop requests and closing during capture.
        # Keep a fake worker alive long enough to inspect its identity and cooperative stop flag.
        # The UI must not launch a second worker or disappear before the first has finished writing.
        root=tk.Tk();root.withdraw();entered=threading.Event();finish=threading.Event()
        def capture(boss,folder,**options):
            # Simulate a slow worker for an unverified named encounter.
            # Assert that the typed name reaches the backend, then wait on a test-owned completion event.
            # This exposes close/start races without opening the game or recording personal data.
            self.assertTrue(boss.startswith('encounter_'))
            self.assertEqual(options['boss_name'],'Onryoki')
            entered.set();finish.wait(3)
        try:
            with tempfile.TemporaryDirectory() as td, patch.object(recorder,'record_encounter',side_effect=capture) as backend:
                app=recorder.Recorder(root,enable_hotkey=False,settings_path=Path(td)/'settings.json')
                app.recordings=Path(td)/'Recordings'
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
        # Check the Recorder layout at small/large windows and three Windows font scales.
        # Inspect widget bounds, a visible sequence row and pixel alignment with the composed wallpaper.
        # Collect Tk callback failures; geometry checks do not claim subjective visual or live-game acceptance.
        for scaling in (1.33,2.0,2.67):
            root=tk.Tk();root.attributes('-alpha',0);root.tk.call('tk','scaling',scaling)
            errors=[];root.report_callback_exception=lambda kind,error,trace: (
                # Collect a Tk callback failure for the enclosing test or smoke receipt.
                # A background UI exception must make validation fail instead of being printed and overlooked.
                # Store readable error text; the callback itself remains on the Tk thread.
                errors.append(str(error))
            )
            try:
                with tempfile.TemporaryDirectory() as td:
                    app=recorder.Recorder(root,enable_hotkey=False,settings_path=Path(td)/'settings.json')
                    for width,height in ((680,650),(960,740),(1400,950)):
                        root.geometry(f'{width}x{height}');root.update()
                        self.assertFalse(errors)
                        self.assertGreaterEqual(app.labels.winfo_height(),round(83*app.scale))
                        self.assertEqual(app.backdrop.picture.width(),app.backdrop.winfo_width())
                        self.assertEqual(app.backdrop.picture.height(),app.backdrop.winfo_height())
                        self.assertEqual(app.help_label.photo.get(0,0),app.backdrop.crop(app.help_label).getpixel((0,0)))
                        for widget in (app.selector,app.primary,app.help_label,app.labels,app.description,app.save_button,*app.idle_buttons[:3]):
                            self.assertGreater(widget.winfo_width(),20)
                            self.assertGreaterEqual(widget.winfo_rootx(),root.winfo_rootx())
                            self.assertLessEqual(widget.winfo_rootx()+widget.winfo_width(),root.winfo_rootx()+root.winfo_width())
                            self.assertLessEqual(widget.winfo_rooty()+widget.winfo_height(),root.winfo_rooty()+root.winfo_height())
                    app.close()
            finally:
                try: root.destroy()
                except tk.TclError: pass

    def test_export_is_background_work_and_close_waits_for_it(self):
        # Hold an export worker open while exercising UI events and close.
        # Verify hotkey toggles do not replace the exporter and shutdown waits for it.
        # A responsive window must not come at the cost of truncating evidence writes.
        root=tk.Tk();root.withdraw();entered=threading.Event();finish=threading.Event()
        def export(folder,path):
            # Provide a controllably slow collection exporter for the lifecycle test.
            # Signal that background work began and wait until the test permits completion.
            # Return the requested destination without writing a real archive or accessing user sessions.
            entered.set();finish.wait(3);return path
        try:
            with tempfile.TemporaryDirectory() as td, patch.object(recorder,'export_sessions',side_effect=export):
                app=recorder.Recorder(root,enable_hotkey=False,settings_path=Path(td)/'settings.json');app.folder=Path(td)
                app.export([app.folder]);self.assertTrue(entered.wait(1));self.assertEqual(app.operation,'export')
                worker=app.thread;app.toggle();self.assertIs(app.thread,worker)
                root.update();app.close();self.assertTrue(root.winfo_exists())
                finish.set();worker.join(2);app.close()
        finally:
            finish.set()
            try: root.destroy()
            except tk.TclError: pass

    def test_global_hotkey_registration_conflict_and_release_without_key_input(self):
        # Register the same custom shortcut on separate Windows threads.
        # Check that the second registration reports a conflict and a later registration succeeds after release.
        # The test uses registration APIs only, without generating keys or controlling Nioh.
        events=[];first=GlobalHotkey('Ctrl+Alt+K',lambda kind,value: (
            # Collect the first listener's registration events in arrival order.
            # Retain both event kind and message so the test can distinguish readiness from failure.
            # This observes the hotkey worker without generating a physical key press.
            events.append((kind,value))
        ))
        # Register on separate threads; no key presses, hooks or game access.
        try:
            import time
            deadline=time.monotonic()+2
            while not events and time.monotonic()<deadline: time.sleep(.01)
            self.assertEqual(events[0][0],'hotkey_ready')
            conflict=[];second=GlobalHotkey('Ctrl+Alt+K',lambda kind,value: (
                # Collect the second listener's registration outcome.
                # Its failure message demonstrates a real Windows shortcut conflict with the first listener.
                # Recording remains fake and no key is delivered to Nioh.
                conflict.append((kind,value))
            ))
            second.thread.join(2);second.close()
            self.assertEqual(conflict[0][0],'hotkey_error')
        finally: first.close()
        released=[];third=GlobalHotkey('Ctrl+Alt+K',lambda kind,value: (
            # Collect events from the listener started after the old registration is closed.
            # The readiness result proves the shortcut was actually released for reuse.
            # No keyboard input is synthesized to establish registration ownership.
            released.append((kind,value))
        ))
        try:
            deadline=time.monotonic()+2
            while not released and time.monotonic()<deadline: time.sleep(.01)
            self.assertEqual(released[0][0],'hotkey_ready')
        finally: third.close()

    def test_unknown_boss_name_survives_export_and_intake_without_verification(self):
        # Round-trip a custom Unicode encounter name through export and intake.
        # Check the readable name and pending identity confidence in the resulting report.
        # Unknown names must remain useful context without becoming unsupported boss fingerprints.
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
        # Simulate a disk failure while writing a single-session ZIP.
        # Run the production exporter and inspect the requested destination afterward.
        # Only a successfully closed archive may appear as a shareable export.
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
            stage_product(ROOT.parent/'SKM',destination)
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
        # Submit repeated raw evidence and then a conflicting annotation revision.
        # Check entry counts, raw-byte deduplication and overlapping-label conflicts.
        # The report remains pending and source captures stay unchanged even when reconstruction is internally consistent.
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
        # Modify a hashed raw take or add an unsupported path to an otherwise valid ZIP.
        # Use the production member/hash validator on each altered submission.
        # Neither variant may create an intake destination or escape into another filesystem path.
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
        # Reconstruct a repeated action pair with a known native transition condition.
        # Check that the report retains the condition and distinguishes native-link evidence from temporal ordering.
        # A paired-contact hint remains a review candidate, not proof that William can execute that combo.
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
