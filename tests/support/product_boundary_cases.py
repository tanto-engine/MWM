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
from contextlib import nullcontext
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT.parent/'tanto-recorder/src')]
from build_product import READ_ONLY, stage_product
import build_product
from recording_bundle import intake_bundle, session_summary, export_sessions, export_capture
from encounter_recording import save_annotation, BOSSES, DEFAULT_SIGNATURES
from action_capture import Journal, sample, publish
from encounter_recording_cases import state, metadata

class ProductBoundaryTests(unittest.TestCase):
    def test_sampler_ignores_transient_transition_fields_and_recovers_previous(self):
        from types import SimpleNamespace
        game = SimpleNamespace(identity=dict(pid=1), tick=-1, reads=0)
        def alive():
            game.tick += 1
            return game.tick < 2
        def snapshot(address):
            game.reads += 1
            return b'', dict(owner_like='0x30000', current=hex(0x40000 + game.tick * 0x1000),
                             previous='0x60000', counter=(1, 4)[game.tick], pending_index=game.reads)
        def read(address, size):
            return struct.pack('<I', address // 0x1000) + bytes(size - 4)
        game.alive, game.snapshot, game.bytes = alive, snapshot, read
        with tempfile.TemporaryDirectory() as td:
            journal = Journal(Path(td)/'events.jsonl', 'one')
            try:
                sample(game, journal, threading.Event(), initial=dict(candidates=[dict(object='0x10000', owner_like='0x30000')]), metadata_factory=lambda: nullcontext(game))
            finally: journal.close()
            rows = [json.loads(line) for line in (Path(td)/'events.jsonl').read_text().splitlines()]
            actions = [row for row in rows if row['kind'] == 'action_state']
            self.assertEqual(len(actions), 2)
            self.assertEqual(actions[-1]['descriptor']['action_key_u32'], 0x41)
            gaps = [row for row in rows if row['kind'] == 'counter_gap']
            self.assertEqual(gaps[0]['unobserved_increments'], 2)
            previous = [row for row in rows if row['kind'] == 'previous_action']
            self.assertEqual(previous[-1]['descriptor']['action_key_u32'], 0x60)
            self.assertEqual(previous[-1]['provenance'], 'inferred_previous_pointer')
            self.assertNotIn('execution_t', previous[-1])

    def test_optional_metadata_cannot_block_other_actor_ids(self):
        import time
        from types import SimpleNamespace
        entered, release = threading.Event(), threading.Event()
        game = SimpleNamespace(identity=dict(pid=1), tick=0)
        def alive():
            game.tick += 1
            if game.tick == 2:
                self.assertTrue(entered.wait(1))
            return game.tick <= 3
        def snapshot(address):
            return b'', dict(owner_like='0x30000', current='0x40000', counter=game.tick)
        raw = struct.pack('<I', 0x12345678) + bytes(0xD0-4)
        game.alive, game.snapshot, game.bytes = alive, snapshot, lambda address,size: raw[:size]
        reader = SimpleNamespace(identity=game.identity, snapshot=snapshot, bytes=game.bytes)
        def slow_metadata(*args):
            entered.set()
            release.wait(2)
            return dict(descriptor_bytes=raw.hex())
        with tempfile.TemporaryDirectory() as td, patch('boss_probe.metadata', side_effect=slow_metadata):
            journal = Journal(Path(td)/'events.jsonl', 'one')
            started = time.monotonic()
            try:
                sample(game, journal, threading.Event(), initial=dict(candidates=[
                    dict(object=hex(actor), owner_like='0x30000') for actor in (0x10000,0x20000)]),
                    metadata_factory=lambda: nullcontext(reader))
                self.assertEqual(journal.actions, 6)
                self.assertGreater(journal.quality['dropped_events'], 0)
                self.assertLess(time.monotonic()-started, 1)
            finally:
                release.set(); journal.close()

    def test_metadata_process_identity_mismatch_is_not_accepted(self):
        from action_capture import MetadataReader
        from types import SimpleNamespace
        reader = MetadataReader(lambda: nullcontext(SimpleNamespace(identity=dict(pid=2))), dict(pid=1))
        try:
            task, detail, error = reader.results.get(timeout=1)
            self.assertIsNone(task)
            self.assertIsNone(detail)
            self.assertIn('process changed', error)
        finally: reader.close()

    def test_read_only_metadata_keeps_full_payload_and_matching_timing_events(self):
        from boss_probe import metadata as capture_metadata, resource_match
        from boss_probe_cases import FakeBytes
        descriptor, body = bytearray(0xD0), bytearray(0xB0)
        struct.pack_into('<Q', descriptor, 0x20, 0x20000)
        struct.pack_into('<i', body, 0x20, 1220)
        struct.pack_into('<i', body, 0x34, -1)
        body[-1] = 93
        wrapper = struct.pack('<QQ', 0x40000, 0x50000)
        hashed = struct.pack('<IIQQ', 0,0,1,0x60000)
        data = bytearray(0x24); struct.pack_into('<I', data, 0x14, 1); struct.pack_into('<I', data, 0x20, 0x30)
        prefix = struct.pack('<4I', 0,1,16,0)
        events = bytes(range(12))
        game = FakeBytes({0x10000:descriptor,0x20000:body,0x30000:wrapper,0x40000:data,
                          0x40030:struct.pack('<I',0x100),0x40100:prefix+events,
                          0x50000:hashed,0x60000:struct.pack('<ii',1220,0)})
        result = capture_metadata(game,0x10000)
        self.assertEqual(bytes.fromhex(result['payload_bytes']),body)
        self.assertTrue(result['payload_stable'])
        timing = resource_match(game,0x30000,1220,True)
        self.assertEqual(timing['events'],events.hex())
        self.assertEqual(timing['indexes'],[0])

    def test_saved_health_carries_measured_quality(self):
        with tempfile.TemporaryDirectory() as td, patch('builtins.print') as output:
            journal = Journal(Path(td)/'events.jsonl', 'one')
            try:
                journal.quality.update(counter_gaps=5, recovered_previous=1, discovery_complete=True)
                publish(journal, 'stopped', 'Saved')
                report = json.loads(output.call_args.args[0])
                self.assertEqual(report['quality']['counter_gaps'], 5)
                self.assertEqual(report['quality']['recovered_previous'], 1)
                self.assertTrue(report['quality']['discovery_complete'])
            finally: journal.close()

    def test_optional_metadata_rejects_changed_lifetime_or_descriptor(self):
        from action_capture import MetadataReader
        from types import SimpleNamespace
        raw = struct.pack('<I', 0x12345678) + bytes(0xD0-4)
        for mutation in ('owner', 'reset', 'descriptor'):
            state = dict(owner_like='0x30000', current='0x40000', counter=5)
            memory = [raw]
            reader = SimpleNamespace(identity=dict(pid=1), snapshot=lambda address: (b'',dict(state)),
                                     bytes=lambda address,size: memory[0][:size])
            def mutate(*args):
                if mutation == 'owner': state['owner_like'] = '0x50000'
                elif mutation == 'reset': state['counter'] = 0
                else: memory[0] = bytes(0xD0)
                return dict(descriptor_bytes=raw.hex())
            with patch('boss_probe.metadata', side_effect=mutate), patch('boss_probe.actor_metadata', return_value={}):
                worker = MetadataReader(lambda: nullcontext(reader), reader.identity)
                try:
                    worker.tasks.put(dict(actor=0x10000,owner='0x30000',descriptor=0x40000,counter=5,prefix=raw[:0x28]))
                    task, detail, error = worker.results.get(timeout=1)
                    self.assertIsNone(detail, mutation)
                    self.assertIn('changed', error, mutation)
                finally: worker.close()

    def test_async_metadata_matches_original_generation_after_newer_action(self):
        from encounter_recording import reconstruct_capture
        first = state(.1, generation=1, counter=1, take='one')
        second = state(.2, 0xC66, generation=1, counter=2, take='one', current='0x50000')
        detail = metadata(t=.3, generation=1, take='one', observation_t=.1, observation_counter=1)
        prefix = detail['descriptor_bytes'][:0x28*2]
        first['descriptor_prefix'] = prefix
        detail['observation_signature'] = prefix
        with tempfile.TemporaryDirectory() as td:
            source = Path(td)/'events.jsonl'
            repeat = dict(first, t=.15, counter=2)
            source.write_text('\n'.join(json.dumps(row) for row in [first,repeat,second,detail]))
            result = reconstruct_capture(source,'okatsu')
            rows = {row['source']['action_id']:row for row in result['actions']}
            self.assertEqual(rows[0xC64]['source']['motion_id'],1220)
            self.assertEqual(rows[0xC64]['observations'],2)
            self.assertIsNone(rows[None]['source']['motion_id'])
            detail['generation'] = 2
            source.write_text('\n'.join(json.dumps(row) for row in [first,second,detail]))
            result = reconstruct_capture(source,'okatsu')
            self.assertTrue(all(row['source']['motion_id'] is None for row in result['actions']))

    def test_capture_gaps_and_actor_generations_do_not_form_invented_combos(self):
        from encounter_recording import reconstruct_capture
        rows = [state(.1, generation=1), metadata(),
                dict(kind='counter_gap',object='0x10000',unobserved_increments=2,t=.2),
                dict(kind='previous_action',object='0x10000',descriptor=dict(action_key_u32=999),t=.2),
                state(.3,0xC66,generation=1),metadata(0xC66,1230,t=.31),
                dict(kind='actor_generation',object='0x10000',generation=2,t=.4),
                state(.5,generation=2),metadata(t=.51)]
        with tempfile.TemporaryDirectory() as td:
            source = Path(td)/'events.jsonl'
            source.write_text('\n'.join(json.dumps(row) for row in rows))
            result = reconstruct_capture(source,'okatsu')
            self.assertEqual(result['observed_successors'],[])
            self.assertEqual(len({row['actor_label'] for row in result['actions']}),2)
            self.assertNotIn(999,{row['source']['action_id'] for row in result['actions']})

    def test_recorder_source_stamps_cover_capture_and_metadata_code(self):
        from action_capture import source_stamp
        stamp = source_stamp()
        self.assertEqual(stamp['protocol'], 2)
        self.assertIn('sample', stamp['runtime_sha256'])
        self.assertIn('MetadataReader.run', stamp['runtime_sha256'])
        self.assertIn('actor_metadata', stamp['runtime_sha256'])
        self.assertTrue(all(len(value) == 64 for value in stamp['runtime_sha256'].values()))
        self.assertEqual(stamp, source_stamp())

    def test_failed_optional_metadata_retries_on_later_observed_execution(self):
        from types import SimpleNamespace
        raw = struct.pack('<I', 0x12345678) + bytes(0xD0-4)
        game = SimpleNamespace(identity=dict(pid=1), tick=0)
        def alive():
            game.tick += 1
            return game.tick <= 8
        def snapshot(address):
            return b'', dict(owner_like='0x30000',current='0x40000',counter=game.tick)
        game.alive, game.snapshot, game.bytes = alive, snapshot, lambda address,size: raw[:size]
        reader = SimpleNamespace(identity=game.identity,snapshot=snapshot,bytes=game.bytes)
        with tempfile.TemporaryDirectory() as td, \
             patch('boss_probe.metadata', side_effect=[OSError('Temporary metadata loss'),dict(descriptor_bytes=raw.hex())]) as capture, \
             patch('boss_probe.actor_metadata', return_value={}):
            journal = Journal(Path(td)/'events.jsonl','one')
            try:
                sample(game,journal,threading.Event(),initial=dict(candidates=[dict(object='0x10000',owner_like='0x30000')]),
                       metadata_factory=lambda: nullcontext(reader))
                self.assertEqual(capture.call_count,2)
                self.assertEqual(journal.actions,8)
                self.assertEqual(journal.quality['metadata_failures'],1)
            finally: journal.close()
            rows = [json.loads(line) for line in (Path(td)/'events.jsonl').read_text().splitlines()]
            self.assertEqual(sum(row['kind']=='metadata' for row in rows),1)

    def test_optional_reader_failure_is_visible_without_losing_ids(self):
        from types import SimpleNamespace
        game = SimpleNamespace(identity=dict(pid=1),tick=0)
        def alive():
            game.tick += 1
            return game.tick <= 3
        game.alive = alive
        game.snapshot = lambda address: (b'',dict(owner_like='0x30000',current='0x40000',counter=game.tick))
        game.bytes = lambda address,size: struct.pack('<I',0x12345678)+bytes(size-4)
        with tempfile.TemporaryDirectory() as td:
            journal = Journal(Path(td)/'events.jsonl','one')
            try:
                sample(game,journal,threading.Event(),initial=dict(candidates=[dict(object='0x10000',owner_like='0x30000')]),
                       metadata_factory=lambda: nullcontext(SimpleNamespace(identity=dict(pid=2))))
                self.assertEqual(journal.actions,3)
                self.assertEqual(journal.quality['metadata_failures'],1)
            finally: journal.close()

    def test_recorder_capture_feedback(self):
        import subprocess
        result = subprocess.run(['node', str(ROOT.parent/'tanto-recorder/desktop/capture-state.test.cjs')],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_desktop_context_hotkey_and_portable_runtime_boundaries(self):
        # Reuse actual TypeScript handlers with fake Electron and process boundaries.
        # Keep fixture settings and recordings isolated from the user's currently running EXE.
        # This remains part of the existing offline entrypoint, with no game or OS key interaction.
        import subprocess
        with tempfile.TemporaryDirectory() as folder:
            result = subprocess.run(['node', str(ROOT/'tests/desktop/recorder_workflow.cjs'), folder],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_reused_actor_counter_reset_refreshes_its_cached_metadata(self):
        # Replay the observed retry pattern: same node, owner and descriptor, but counter restarts.
        # Optional payload bytes can change at reused addresses and must be read again after reset.
        # Preserve both full IDs and record a reset without inventing a death classification.
        from types import SimpleNamespace
        from unittest.mock import Mock
        game = SimpleNamespace(identity=dict(pid=1), tick=-1)
        raw = struct.pack('<I', 0x12345678) + bytes(0xD0 - 4)
        states = [dict(owner_like='0x30000', current='0x40000', counter=value) for value in (25, 0)]

        def alive():
            # Advance through the two recorded lifetimes without using a real game process.
            # Each sampling pass sees stable before/after bytes at the same virtual address.
            # End deterministically after the reset has been sampled.
            game.tick += 1
            return game.tick < len(states)

        def snapshot(address):
            # Return the state for this sampling pass, including its restarted counter.
            # Repeated coherence reads see the same frame of the fixture.
            # Address and owner deliberately remain unchanged across the reset.
            return b'', states[game.tick]

        game.alive, game.snapshot, game.bytes = alive, snapshot, Mock(return_value=raw)
        with tempfile.TemporaryDirectory() as td, patch('boss_probe.metadata', return_value=dict(descriptor_bytes=raw.hex())) as metadata_read:
            path = Path(td) / 'events.jsonl'; journal = Journal(path, 'one')
            try: sample(game, journal, threading.Event(), initial=dict(candidates=[dict(object='0x10000', owner_like='0x30000')]), metadata_factory=lambda: nullcontext(game))
            finally: journal.close()
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual(metadata_read.call_count, 2)
            resets = [row for row in rows if row['kind'] == 'actor_reset']
            self.assertEqual([(row['previous_counter'], row['counter'], row['cause']) for row in resets], [(25, 0, 'unverified')])
            self.assertEqual(sum(row['kind'] == 'action_state' for row in rows), 2)
            self.assertEqual(len({row['generation'] for row in rows if row['kind'] == 'action_state'}), 2)
            self.assertEqual(journal.quality['counter_gaps'], 0)

    def test_rebuilt_actor_resumes_while_the_full_heap_scan_is_still_running(self):
        # Model death/retry moving the actor into a nearby slot during a long full scan.
        # The first scan's cumulative snapshot stays old; only local rediscovery can find the replacement.
        # A single take must save both actors without waiting for that full scan to finish.
        from contextlib import nullcontext
        from types import SimpleNamespace
        from unittest.mock import Mock
        import time
        stop = threading.Event()
        observed = {0x10000: threading.Event(), 0x11000: threading.Event()}
        raw = struct.pack('<I', 0x12345678) + bytes(0xD0 - 4)
        game = SimpleNamespace(identity=dict(pid=1), phase=0, alive=Mock(return_value=True), bytes=Mock(return_value=raw))

        def snapshot(address):
            # A rebuilt enemy occupies a new slot; the old address is no longer an action node.
            # Keep its descriptor stable within each phase so the normal coherence check applies.
            # This changes actor lifetime without changing the game process identity.
            if address != (0x10000 if game.phase == 0 else 0x11000): raise OSError('retired actor')
            return b'', dict(owner_like='0x30000', current='0x40000', counter=game.phase)

        def discover(reader, seed=None, stop_requested=None, on_progress=None):
            # Return fresh nearby candidates when requested, but stall the simulated whole-heap scan.
            # Release the replacement only through the new local revalidation path.
            # Bound each wait so a regression fails promptly rather than hanging the suite.
            old = dict(candidates=[dict(object='0x10000', owner_like='0x30000')])
            if seed is not None:
                return dict(candidates=[dict(object='0x11000', owner_like='0x30000')])
            on_progress(old)
            observed[0x10000].wait(1)
            game.phase = 1
            time.sleep(1.05)
            on_progress(old)
            observed[0x11000].wait(.5)
            stop.set()
            return old

        game.snapshot = snapshot
        with tempfile.TemporaryDirectory() as td, patch('boss_probe.discover', side_effect=discover), \
             patch('boss_probe.metadata', side_effect=OSError('optional metadata')), patch('builtins.print'):
            path = Path(td) / 'events.jsonl'; journal = Journal(path, 'one')
            emit = journal.emit

            def record(kind, **fields):
                # Save real journal rows before acknowledging observation to the scan fixture.
                # Signal only primary action IDs, never candidate discovery or metadata.
                # The final assertion therefore requires durable observations from both lifetimes.
                emit(kind, **fields)
                if kind == 'action_state': observed[int(fields['object'], 0)].set()

            journal.emit = record
            try: sample(game, journal, stop, discover_factory=Mock(return_value=nullcontext(game)))
            finally: journal.close()
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual({row['object'] for row in rows if row['kind'] == 'action_state'}, {'0x10000', '0x11000'})

    def test_unexpected_discovery_failure_is_saved_instead_of_silencing_the_thread(self):
        # A programming error in the scan thread must become evidence, not endless zero-ID health.
        # Stop as soon as the sampler journals that error; the two-second guard bounds a broken regression.
        # Exercise the real thread/mailbox path without attaching to a process or reading game memory.
        from contextlib import nullcontext
        from types import SimpleNamespace
        from unittest.mock import Mock
        game = SimpleNamespace(identity=dict(pid=1), alive=Mock(return_value=True))
        stop = threading.Event()
        guard = threading.Timer(2, stop.set)
        with tempfile.TemporaryDirectory() as td, patch('boss_probe.discover', side_effect=RuntimeError('scan failed')), patch('builtins.print'):
            path = Path(td) / 'events.jsonl'; journal = Journal(path, 'one')
            emit = journal.emit

            def record(kind, **fields):
                # Keep production journal writes and their real serialized error detail.
                # End the fixture only once the main sampler receives a scan diagnostic.
                # An exception stranded in the background thread cannot satisfy this condition.
                emit(kind, **fields)
                if kind == 'diagnostic': stop.set()

            journal.emit = record
            guard.start()
            try:
                sample(game, journal, stop, discover_factory=Mock(return_value=nullcontext(game)))
            finally:
                guard.cancel(); journal.close()
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertTrue(any(row.get('code') == 'discovery' and row.get('detail') == 'RuntimeError: scan failed' for row in rows))

    def test_action_journal_preserves_crash_tail_and_excludes_second_writer(self):
        # Resume a journal whose last line was cut short, without erasing any existing bytes.
        # Reject a second writer, then allow another take after the first releases its lock.
        # One journal retains both takes; no status, lock or reconstruction sidecar is required.
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'events.jsonl'
            earlier = b'{"kind":"end","take":"older","t":1}\n{"kind":'
            path.write_bytes(earlier)
            first = Journal(path, 'first')
            try:
                with self.assertRaises(OSError): Journal(path, 'competing')
                first.emit('action_state', object='0x10000',
                           descriptor=dict(action_key_u32=0x12345678, action_key_hex='0x12345678'))
            finally:
                first.close()
            second = Journal(path, 'second')
            try: second.emit('end', actions=0)
            finally: second.close()
            raw = path.read_bytes()
            self.assertTrue(raw.startswith(earlier + b'\n'))
            rows = [json.loads(line) for line in raw.splitlines() if line != b'{"kind":']
            self.assertEqual([row['take'] for row in rows], ['older', 'first', 'second'])
            self.assertEqual(rows[1]['descriptor']['action_key_u32'], 0x12345678)
            self.assertEqual([p.name for p in Path(td).iterdir()], ['events.jsonl'])

    def test_sampler_keeps_full_ids_when_other_actors_and_metadata_fail(self):
        # Supply one readable actor and one expired actor without any boss fingerprint.
        # Make optional metadata fail on every action; primary IDs must still be journaled.
        # Bounded fake frames exercise the production sampler without opening a game process.
        import itertools
        class Game:
            identity = dict(pid=1, build_sha256='fixture')
            ticks = 0
            def alive(self):
                # End the fake process after three sampling ticks.
                # Each tick changes the action counter, making a fresh observable state.
                # This bounds the fixture without sleeping or a real process handle.
                self.ticks += 1
                return self.ticks <= 3
            def snapshot(self, address):
                # Return stable before/after state for the surviving actor in this tick.
                # The second candidate behaves like an enemy whose native object disappeared.
                # Its failure must not prevent collecting the remaining actor's IDs.
                if address == 0x20000: raise OSError('Actor disappeared')
                return b'', dict(owner_like='0x30000', current='0x40000', counter=self.ticks)
            def bytes(self, address, size):
                # Supply a complete action descriptor with a nonzero upper word in its key.
                # No native address is dereferenced; this is an ordinary fixture byte array.
                # The large key detects accidental narrowing to the low 16 bits.
                raw = bytearray(size)
                struct.pack_into('<I', raw, 0, 0x12345678)
                return bytes(raw)
        with tempfile.TemporaryDirectory() as td, patch('action_capture.time.monotonic', side_effect=itertools.count(0, .2)), \
             patch('boss_probe.metadata', side_effect=OSError('Optional table disappeared')), patch('builtins.print'):
            path = Path(td) / 'events.jsonl'; journal = Journal(path, 'one')
            try:
                initial = dict(candidates=[dict(object=hex(address), owner_like='0x30000') for address in (0x10000, 0x20000)])
                sample(Game(), journal, threading.Event(), initial=initial)
            finally: journal.close()
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            actions = [row for row in rows if row['kind'] == 'action_state']
            self.assertEqual(len(actions), 3)
            self.assertTrue(all(row['descriptor']['action_key_u32'] == 0x12345678 and row['role'] == 'unassigned' for row in actions))
            self.assertEqual(sum(row['kind'] == 'metadata_unreadable' for row in rows), 0)  # No optional reader was supplied.
            self.assertEqual(sum(row['kind'] == 'object_unreadable' for row in rows), 1)

    def test_saved_health_is_not_published_after_a_failed_disk_sync(self):
        # Simulate a disk-full checkpoint after an action entered the file buffer.
        # The saved-count health channel must stay silent when durability was not established.
        # Releasing the fault allows close to retain earlier bytes and release ownership.
        with tempfile.TemporaryDirectory() as td:
            journal = Journal(Path(td) / 'events.jsonl', 'one')
            try:
                journal.emit('action_state', object='0x10000',
                             descriptor=dict(action_key_u32=1, action_key_hex='0x00000001'))
                with patch('action_capture.os.fsync', side_effect=OSError('Disk full')), patch('builtins.print') as output:
                    with self.assertRaises(OSError): publish(journal, 'recording', 'Saved')
                    output.assert_not_called()
            finally: journal.close()

    def test_v2_archive_retains_drafts_empty_sessions_and_all_actor_evidence(self):
        # Put a two-file capture and a legacy draft-only session in one ordinary ZIP.
        # Compare every retained byte, count all actor roles and flag missing/truncated evidence.
        # Hash failure must not publish a submission; accepted notes never update playable definitions.
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            sessions = [dict(path='sessions/0001-jin', recording_id='jin', boss_name='Jin Hayabusa'),
                        dict(path='sessions/0002-empty', recording_id='empty', boss_name='Maria')]
            files = {}
            for entry in sessions:
                files[entry['path']+'/encounter.json'] = json.dumps(dict(schema_version=2 if entry['recording_id']=='jin' else 1,
                    recording_id=entry['recording_id'], boss_id=entry['recording_id'], boss_name=entry['boss_name'],
                    annotations=[], draft=dict(text=''))).encode()
            raw = b'{"kind":"action_state","role":"unassigned","take":"a","t":1}\n{"kind":"action_state","role":"player_candidate","take":"a","t":2}\n{"kind":'
            files['sessions/0001-jin/events.jsonl'] = raw
            # A migrated session's inline draft is current; its retained old sidecar is historical evidence.
            files['sessions/0001-jin/draft.json'] = b'{"text":"Superseded legacy draft"}'
            files['sessions/0002-empty/draft.json'] = b'{"text":"High priority: three cuts"}'
            manifest = dict(schema_version=2, kind='tanto_session_archive', sessions=sessions,
                files=[dict(path=name, size=len(data), sha256=hashlib.sha256(data).hexdigest()) for name, data in files.items()])
            for tampered in (False, True):
                archive_path = base / ('bad.zip' if tampered else 'good.zip')
                with zipfile.ZipFile(archive_path, 'w') as archive:
                    archive.writestr('manifest.json', json.dumps(manifest))
                    for name, data in files.items(): archive.writestr(name, data + b' ' if tampered else data)
                if tampered:
                    with self.assertRaises(ValueError): intake_bundle(archive_path, base/'rejected')
                    self.assertFalse(list((base/'rejected/submissions').glob('*/review.json')))
                    continue
                report = intake_bundle(archive_path, base/'accepted')
                self.assertFalse(report['curated_changes'])
                self.assertEqual([row['action_rows'] for row in report['sessions']], [2, 0])
                self.assertTrue(report['sessions'][1]['no_raw_evidence'])
                self.assertTrue(report['sessions'][1]['has_draft'])
                self.assertFalse(report['sessions'][0]['has_draft'])
                self.assertEqual(report['sessions'][0]['malformed_event_lines'], 1)
                stored = base/'accepted/submissions'/report['bundle_sha256']
                self.assertTrue(all((stored/name).read_bytes() == data for name, data in files.items()))

    def test_multi_session_export_and_intake_preserve_bosses_takes_and_revisions(self):
        # Export two takes each from two same-boss sessions and another boss, with repeated folder names.
        # Check ZIP integrity, every take's exact bytes, saved revisions, intake and evidence deduplication.
        # Keep session identities separate and preserve original files, even when raw captures match across bosses.
        with tempfile.TemporaryDirectory() as td:
            base=Path(td);folders=[];originals={}
            for index,boss in enumerate(('okatsu','okatsu','maria')):
                folder=base/str(index)/'same-name';folder.mkdir(parents=True);folders.append(folder)
                (folder/'encounter.json').write_text(json.dumps(dict(boss_id=boss,boss_name=boss.title(),recording_id=str(index),created_at=1)))
                for number in (1,2):
                    take=folder/f'take-{number:04d}';take.mkdir()
                    (take/'events.jsonl').write_text(json.dumps(state(number+1)))
                    label=save_annotation(folder,'First description',take.name,0,number+1)
                    save_annotation(folder,f'Revised description {number}',take.name,0,number+1,label_id=label['label_id'])
                originals[folder]={p.relative_to(folder).as_posix():p.read_bytes()
                                   for p in folder.rglob('*') if p.is_file()}
            path=export_sessions(folders,base/'tanto-zips/share.zip')
            report=intake_bundle(path,base/'intake')
            self.assertEqual([item['boss_id'] for item in report['sessions']],['okatsu','okatsu','maria'])
            for index,(folder,item) in enumerate(zip(folders,report['sessions'])):
                self.assertEqual(item['recording_id'],str(index))
                self.assertEqual([take['take'] for take in item['takes']],['take-0001','take-0002'])
                for take in item['takes']:
                    self.assertEqual((base/'intake/captures'/f'{take["sha256"]}.jsonl').read_bytes(),
                                     originals[folder][take['take']+'/events.jsonl'])
                self.assertEqual([(label['take'],label['label'],label['revision']) for label in item['annotations']],
                                 [(f'take-{number:04d}',f'Revised description {number}',2) for number in (1,2)])
            self.assertEqual(intake_bundle(path,base/'intake'),report)
            self.assertEqual(len(list((base/'intake/captures').glob('*.jsonl'))),2)
            self.assertIn('boss_identity',{c['kind'] for c in report['sessions'][2]['conflicts']})
            with zipfile.ZipFile(path) as outer:
                self.assertIsNone(outer.testzip())
                self.assertEqual(len(outer.namelist()),4)
                import io
                for index,folder in enumerate(folders,1):
                    with zipfile.ZipFile(io.BytesIO(outer.read(f'session-{index:04d}.zip'))) as inner:
                        self.assertIsNone(inner.testzip())
                        for name,data in originals[folder].items():
                            if name!='encounter.json':self.assertEqual(inner.read(name),data)
                            self.assertEqual((folder/name).read_bytes(),data)

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

    def test_exe_release_gate_rejects_unversioned_dirty_unpinned_and_reused_builds(self):
        # Exercise release rejection without invoking a compiler or creating an EXE.
        # Vary version syntax, dirty source, Engine pin and an existing version directory.
        # Only traceable clean inputs with an unused version may reach packaging.
        with tempfile.TemporaryDirectory() as td:
            base=Path(td);engine=base/'tanto-engine';engine.mkdir()
            product=base/'tanto-recorder';product.mkdir();(base/'MWM').mkdir()
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

    def test_boss_menu_names_do_not_invent_detection_signatures(self):
        # Check that the broad boss-name menu remains separate from identity verification.
        # Compare named encounters with the small set of configured action/motion fingerprints.
        # A familiar boss label must not make an unverified recording appear identified.
        self.assertGreaterEqual(len(BOSSES),40)
        key,name=next((row['id'],row['name']) for row in BOSSES.values() if row['name']=='Onryoki')
        self.assertEqual(name,'Onryoki');self.assertNotIn(key,DEFAULT_SIGNATURES)
        self.assertEqual(set(DEFAULT_SIGNATURES),{'okatsu','jin_hayabusa','maria'})

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

    def test_unknown_boss_name_survives_export_and_intake_without_verification(self):
        # Round-trip a custom Unicode encounter name through export and intake.
        # Check the readable name and pending identity confidence in the resulting report.
        # Unknown names must remain useful context without becoming unsupported boss fingerprints.
        boss,name='custom_enemy','大蝦蟇'
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
            stage_product(ROOT/'mwm',destination)
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
