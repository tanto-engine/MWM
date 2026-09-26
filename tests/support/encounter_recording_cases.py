import json
from pathlib import Path
import struct
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'runtime'))
import encounter_recording as encounter


def state(t, action=0xC64, **changes):
    # Create an owner-validated boss action observation.
    # Allow individual identity and descriptor fields to be replaced by each test.
    # Reconstruction must not inherit trust from a convenient default actor label.
    event = dict(kind='action_state', t=t, object='0x10000', owner_like='0x20000',
                 current='0x30000', role='boss_candidate', owner_matches_discovery=True,
                 descriptor={'word0_u16': action & 0xFFFF, 'payload': '0x40000'})
    event.update(changes)
    return event


def metadata(action=0xC64, motion=1220, override=-1, **changes):
    # Encode full action, motion and timing-override fields as captured native bytes.
    # Keep descriptor and payload addresses consistent with the preceding state fixture.
    # Tests can separate reliable DWORD identities from unresolved low-word observations.
    descriptor = bytearray(0xD0)
    payload = bytearray(0x38)
    struct.pack_into('<I', descriptor, 0, action)
    struct.pack_into('<i', payload, 0x20, motion)
    struct.pack_into('<i', payload, 0x34, override)
    event = dict(kind='metadata', t=0.15, object='0x10000', address='0x30000', payload='0x40000',
                 matches_preceding_state=True, descriptor_bytes=descriptor.hex(),
                 payload_prefix={'bytes': payload.hex()})
    event.update(changes)
    return event


class ReconstructionTests(unittest.TestCase):
    def test_pause_annotation_anchors_complete_record_without_claiming_boundary(self):
        # Label the last persisted timestamp even while the recorder has a partial next line.
        # Preserve the user's description and keep exact frame boundaries unverified.
        # Repeated descriptions append evidence instead of replacing an earlier label.
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td); take=folder/'take-0001'; take.mkdir()
            (folder/'encounter.json').write_text(json.dumps({'boss_id':'jin_hayabusa'}))
            (take/'events.jsonl').write_text(json.dumps(state(4.5))+'\n{"kind":')
            for text in ['Downward slash, then Flying Swallow','Unsure where string ends']:
                label=encounter.annotate_recent(folder,text)
                self.assertEqual(label['label'],text)
                self.assertEqual(label['last_recorded_t'],4.5)
                self.assertIn('unverified',label['basis'])
            self.assertEqual(len((folder/'labels.jsonl').read_text().splitlines()),2)

    def test_entries_distinguish_repeats_from_state_samples_and_gaps(self):
        # A counter change alone cannot prove that an unchanged action restarted.
        result = self.run_capture([state(.1,counter=1), metadata(), state(.2,counter=1),
            state(.3,counter=2), {'kind':'sampling_gap'}, state(.4,counter=9), metadata()])
        row = result['actions'][0]
        self.assertEqual(row['observations'],4)
        self.assertEqual(row['observed_entries'],0)
        self.assertEqual(row['unverified_reentries'],1)
        self.assertEqual(row['censored_observations'],2)
        self.assertEqual(result['observed_successors'],[])

    def test_identity_changes_prove_entries_but_gaps_do_not_prove_edges(self):
        result=self.run_capture([state(.1),metadata(),state(.2,0xC66),metadata(0xC66,1230,t=.21),
            state(.3),metadata(t=.31),{'kind':'sampling_gap'},state(.4,0xC66),metadata(0xC66,1230,t=.41)])
        rows={row['source']['action_id']:row for row in result['actions']}
        self.assertEqual(rows[0xC64]['observed_entries'],1)
        self.assertEqual(rows[0xC66]['observed_entries'],1)
        self.assertEqual(sum(edge['count'] for edge in result['observed_successors']),2)

    def test_interval_annotation_revisions_keep_raw_capture_and_prior_labels(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);take=folder/'take-0001';take.mkdir()
            (folder/'encounter.json').write_text(json.dumps({'boss_id':'jin_hayabusa'}))
            raw=(json.dumps(state(5))+'\n{"kind":').encode()
            (take/'events.jsonl').write_bytes(raw)
            first=encounter.save_annotation(folder,'Downward slash',take.name,1,3,markers=['unsure'])
            revised=encounter.save_annotation(folder,'Slash then jump',take.name,1,4,
                markers=['repeat','interrupted'],label_id=first['label_id'])
            current=encounter.load_annotations(folder)
            self.assertEqual(len(current),1)
            self.assertEqual(current[0],revised)
            self.assertEqual(revised['revision'],first['revision']+1)
            self.assertEqual((revised['start_t'],revised['end_t']),(1,4))
            self.assertEqual(len((folder/'labels.jsonl').read_text().splitlines()),2)
            self.assertEqual((take/'events.jsonl').read_bytes(),raw)
            for start,end in [(-1,2),(3,2),(0,6),(0,float('nan')),(0,float('inf'))]:
                with self.assertRaises(ValueError):
                    encounter.save_annotation(folder,'Invalid',take.name,start,end)
            with self.assertRaises(ValueError):
                encounter.save_annotation(folder,'Invalid',take.name,0,2,markers=['confirmed'])
            with self.assertRaises(ValueError):
                encounter.save_annotation(folder,'Invalid','../take-0001',0,2)
            with self.assertRaises(ValueError):
                encounter.save_annotation(folder,'Invalid',take.name,0,2,label_id='missing')

    def run_capture(self, events, raw_tail=''):
        # Reconstruct a temporary JSONL capture with an optional damaged tail.
        # Write the supplied events exactly as the real recorder would retain them.
        # Recovery behavior must be assessed from persisted evidence rather than predecoded objects.
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / 'events.jsonl'
            source.write_text('\n'.join(json.dumps(e) for e in events) + '\n' + raw_tail, encoding='utf8')
            return encounter.reconstruct_capture(source, 'okatsu')

    def test_trusted_metadata_decodes_full_dword_not_word0(self):
        # Recover full action identities only from trusted consistent metadata.
        # Capture a key whose high bits differ from the observed low word.
        # Trusted raw descriptor bytes must supply the permanent full action identity.
        result = self.run_capture([{'kind': 'session'}, state(0.1), metadata(0x1000C64), {'kind': 'end'}])
        row = result['actions'][0]
        self.assertEqual(row['source']['action_id'], 0x1000C64)
        self.assertEqual(row['source']['observed_word0_u16'], 0xC64)
        self.assertEqual(row['source']['motion_id'], 1220)
        self.assertEqual(row['source']['timing_id'], 1220)
        self.assertTrue(result['complete'])
        self.assertNotIn('0x30000', json.dumps(result))

    def test_failed_metadata_consistency_does_not_promote_low_word(self):
        # Keep inconsistent metadata from promoting a low-word observation.
        # Vary the metadata consistency flag, descriptor address and payload address separately.
        # An unverified low word must remain unresolved rather than become a full source key.
        for change in [dict(matches_preceding_state=False), dict(address='0x99999'), dict(payload='0x99999')]:
            result = self.run_capture([state(0.1), metadata(**change)])
            self.assertIsNone(result['actions'][0]['source']['action_id'])

    def test_timing_override_decodes_separately(self):
        # Decode a timing override separately from the animation identity.
        # Set a timing override distinct from the payload's animation id.
        # Catalogue references must retain timing selection independently of motion identity.
        result = self.run_capture([state(0.1), metadata(override=7000)])
        self.assertEqual(result['actions'][0]['source']['timing_id'], 7000)

    def test_native_links_preserve_gates_instead_of_promoting_temporal_combos(self):
        # Decode four native row mechanisms while preserving their conditions and signed windows.
        # Keep disabled and unfamiliar rows alongside proven input, completion and contact gates.
        # Permanent source links must contain neither transient pointers nor a duplicate target list.
        rows=[]
        for mode,input_id,condition,target,flags,end in [(0,23,0xD5,0xD5F,0x200002,65),
                (1,255,65535,0xC7A,4,32767),(0,255,22,0x361,0,32767),
                (2,255,0xCF,-1,0x80000000,26)]:
            body=bytearray([255]*48); struct.pack_into('<5H',body,0,condition,*([65535]*4))
            body[10]=mode; body[11]=input_id
            struct.pack_into('<h',body,0x14,target); struct.pack_into('<Ihh',body,0x1C,flags,-32768,end)
            rows.append({'slice_index':len(rows),'address':'0x99999','bytes':body.hex()})
        event=metadata(transition_entries=rows,transition_slice={'count':75},entries_omitted=71)
        source=self.run_capture([state(.1),event])['actions'][0]['source']
        links=source['transition_links']
        self.assertEqual([row['kind'] for row in links],['native_input','animation_end','paired_contact','conditional'])
        self.assertEqual(links[3]['target_action_id'],-1)
        self.assertEqual(links[3]['conditions'],[0xCF,65535,65535,65535,65535])
        self.assertEqual(links[3]['window_frames'],[-32768,26])
        self.assertEqual(links[3]['flags'],0x80000000)
        self.assertEqual(source['transition_rows_total'],75)
        self.assertEqual(source['transition_rows_omitted'],71)
        self.assertNotIn('transition_targets',source)
        self.assertNotIn('0x99999',json.dumps(source))

    def test_contact_and_pulse_metadata_keep_native_widths_and_old_capture_gaps(self):
        # Retain signed contact impulses and complete Pulse timings when their bytes were captured.
        # Decode an older56-byte prefix separately so missing windows cannot become zero defaults.
        # Unknown contact bytes and uint64 flags must survive spreadsheet-safe normalization.
        event=metadata(); payload=bytearray.fromhex(event['payload_prefix']['bytes'])+bytearray(8)
        struct.pack_into('<hh',payload,0x24,-1,60); payload[0x33]=40
        struct.pack_into('<hhh',payload,0x38,60,25,24); event['payload_prefix']['bytes']=payload.hex()
        contact=bytearray(range(128)); struct.pack_into('<Q',contact,0,0x8000000000000080)
        contact[0x16]=6; contact[0x17]=12; contact[0x1A]=7; contact[0x1B]=0xF4
        event.update(combat_entries=[{'slice_index':0,'address':'0x99999','bytes':contact.hex()}],
                     combat_slice={'count':1},combat_entries_omitted=0)
        source=self.run_capture([state(.1),event])['actions'][0]['source']
        self.assertEqual([source[key] for key in ('cancel_frame','ki_pulse_percent','ki_pulse_start','ki_pulse_fill','ki_pulse_hold')],[60,40,60,25,24])
        row=source['combat_rows'][0]
        self.assertEqual([row[key] for key in ('ground_horizontal','ground_vertical','air_horizontal','air_vertical')],[6,12,7,-12])
        self.assertEqual(row['flags'],'0x8000000000000080')
        self.assertEqual(row['raw_hex'],contact.hex())
        self.assertNotIn('0x99999',json.dumps(source))
        old=encounter.decode_action_metadata(metadata())
        self.assertNotIn('ki_pulse_start',old)
        self.assertNotIn('combat_rows',old)

    def test_inconsistent_metadata_is_retained_as_an_issue_not_a_false_action(self):
        # Preserve conflicting metadata as evidence without inventing a resolved action.
        # Pair a C64 state with metadata encoding a different action key.
        # The conflict belongs in retained issues and cannot promote either key as verified.
        result = self.run_capture([state(0.1), metadata(action=0xC66)])
        self.assertIsNone(result['actions'][0]['source']['action_id'])
        self.assertEqual(len(result['issues']), 1)

    def test_every_observation_gap_breaks_strings_and_edges(self):
        # Break reconstructed strings at every recorded observation gap.
        # Insert each supported gap marker between two different observed actions.
        # No temporal successor or string may cross unobserved actor history.
        for kind in ('snapshot_race', 'object_unreadable', 'tracked_actor_changed', 'sampling_gap', 'end', 'session'):
            result = self.run_capture([state(0.1), {'kind': kind, 't': 0.2, 'object': '0x10000'}, state(0.3, 0xC66)])
            self.assertEqual(result['observed_successors'], [], kind)
            self.assertEqual(result['strings'], [], kind)

    def test_repeated_state_is_not_a_followup_and_strings_are_observations(self):
        # Treat repeated states as samples rather than additional combo links.
        # Repeat each of two action states before transitioning between them.
        # Sampling frequency must not inflate combo length or turn temporal order into proven linkage.
        result = self.run_capture([state(0.1), state(0.2), state(0.3, 0xC66), state(0.4, 0xC66)])
        self.assertEqual(len(result['actions']), 2)
        self.assertEqual(len(result['observed_successors']), 1)
        self.assertEqual(result['observed_successors'][0]['relationship'], 'sampled_temporal_order')
        self.assertEqual(len(result['strings'][0]['actions']), 2)

    def test_truncated_tail_retains_every_complete_prior_record(self):
        # Retain every complete event preceding a truncated recording tail.
        # End a JSONL file midway through a later event.
        # Earlier complete actions must remain available while the take stays explicitly incomplete.
        result = self.run_capture([{'kind': 'session'}, state(0.1), state(0.2, 0xC66)], '{"kind":"action')
        self.assertEqual(len(result['actions']), 2)
        self.assertFalse(result['complete'])
        self.assertEqual(result['issues'][0]['line'], 4)

    def test_corrupt_middle_does_not_discard_later_records_or_stitch_edges(self):
        # Continue after a corrupt middle record without joining actions across the gap.
        # Place malformed JSON between two valid action events.
        # Reconstruction must resume afterward but preserve the break in observed continuity.
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / 'events.jsonl'
            source.write_text(json.dumps(state(0.1)) + '\ncorrupt\n' + json.dumps(state(0.3, 0xC66)), encoding='utf8')
            result = encounter.reconstruct_capture(source, 'okatsu')
        self.assertEqual(len(result['actions']), 2)
        self.assertEqual(result['observed_successors'], [])

    def test_unknown_actor_and_unknown_descriptor_survive(self):
        # Preserve unknown actors and unresolved descriptors in reconstruction.
        # Capture an unassigned role and then a state with no descriptor.
        # Unknown data must remain inspectable instead of being discarded or guessed into a move.
        result = self.run_capture([state(0.1, role='unassigned'), state(0.2, descriptor=None)])
        self.assertEqual(result['actions'][0]['role'], 'unassigned')
        self.assertEqual(len(result['unclassified_observations']), 1)

    def test_reused_address_or_changed_role_cannot_inherit_boss_identity(self):
        # Reject reused addresses and changed roles as inherited boss identity.
        # Reuse one object address with a different owner and unassigned role.
        # The new actor label must prevent both inherited boss trust and cross-identity successors.
        result = self.run_capture([state(0.1), state(0.2, 0xC66, owner_like='0x99999', role='unassigned')])
        self.assertEqual(result['actions'][0]['role'], 'boss_candidate')
        self.assertEqual(result['actions'][1]['role'], 'unassigned')
        self.assertNotEqual(result['actions'][0]['actor_label'], result['actions'][1]['actor_label'])
        self.assertEqual(result['observed_successors'], [])

    def test_second_session_without_end_is_not_complete(self):
        # Mark a second session without its own end event as incomplete.
        # Append a new session after a completed one without closing the second.
        # Earlier completion cannot certify a later interrupted take or bridge its action history.
        result = self.run_capture([{'kind': 'session'}, state(0.1), {'kind': 'end'}, {'kind': 'session'}, state(0.1)])
        self.assertFalse(result['complete'])
        self.assertEqual(result['observed_successors'], [])


class SupervisorTests(unittest.TestCase):
    def test_scout_rediscovers_new_actors_while_player_survives(self):
        # Bound unknown-boss takes so an unchanged William cannot hide later spawns.
        # Reveal a new candidate on discovery two and retain both takes' raw events.
        # Identified bosses must retain their long take rather than acquire artificial gaps.
        for boss, duration in ((None, 30), (2, 86400)):
            with self.subTest(boss=boss), tempfile.TemporaryDirectory() as td:
                stop, calls, discoveries = threading.Event(), [], []
                backend = self.backend(stop, calls)
                def discover(*args, **kwargs):
                    # Make the first scan contain William alone and the next include a boss.
                    # Return candidate lists without retiring the player's identity.
                    # This isolates periodic rediscovery from actor-loss recovery.
                    discoveries.append([1] if not discoveries else [1, 3])
                    return {'candidates': discoveries[-1]}
                def select(*args):
                    # Select the same player in both scans with optional known boss identity.
                    # Use the parameterized boss value rather than infer from candidates.
                    # The duration policy must follow identity certainty, not actor count.
                    return 1, boss
                def record(game, cfg, folder, seconds, *args, **kwargs):
                    # Finish the simulated take only when its configured duration is acceptable.
                    # Write each discovered candidate to the real reconstruction input.
                    # Both old and newly spawned actors must survive the take boundary.
                    self.assertEqual(seconds, duration)
                    self.assertEqual(args[-1],128) # Jin's75-row actions must fit one bounded capture.
                    calls.append(folder)
                    folder.mkdir()
                    events = [{'kind': 'session'},
                              *(state(.1, object=hex(actor), role='unassigned') for actor in cfg['candidates']),
                              {'kind': 'end'}]
                    (folder / 'events.jsonl').write_text('\n'.join(map(json.dumps, events)), encoding='utf8')
                    if len(calls) == 2: stop.set()
                    return {'stop_reason': 'duration'}
                backend.update(discover=discover, select=select, record=record)
                encounter.record_encounter('okatsu', td, signature=[] if boss is None else None,
                                           stop_event=stop, retry_seconds=.05, backend=backend)
                self.assertEqual(discoveries, [[1], [1, 3]])
                index = json.loads((Path(td) / 'reconstruction.json').read_text())
                self.assertEqual([take['actions'] for take in index['segments']], [1, 2])
                self.assertTrue(all((take / 'events.jsonl').exists() for take in calls))

    def test_programming_error_surfaces_instead_of_waiting_for_the_game(self):
        # Surface programming errors instead of retrying as if the game were unavailable.
        # Raise KeyError from discovery after setting the cancellation event.
        # The supervisor must surface the defect and publish error state rather than retry forever.
        stop = threading.Event()
        backend = self.backend(stop, [])
        def broken_discovery(*args, **kwargs):
            # Inject a programming KeyError during actor discovery.
            # Set cancellation first so an accidental retry cannot hang the suite.
            # The original error must still escape and leave an explicit nonrunning error status.
            stop.set()
            raise KeyError('bad field')
        backend['discover'] = broken_discovery
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(KeyError, 'bad field'):
                encounter.record_encounter('okatsu', td, stop_event=stop, backend=backend)
            status = json.loads((Path(td) / 'status.json').read_text())
            self.assertEqual(status['state'], 'error')
            self.assertFalse(status['running'])

    def test_runtime_discovery_rejects_stale_process_and_reused_actors(self):
        # Reject stale trace process identity and replaced actor ownership during discovery.
        # Revalidate recent trace actors against process birth, owner, vtable and readability.
        # Only identities proven current may become read-only recording candidates.
        class Game:
            identity = {'pid': 12, 'process_started': 99, 'module_base': '0x50000'}
            def snapshot(self, actor):
                # Return a valid owner only for the first recently observed actor.
                # Make the others change ownership, change vtable or become unreadable.
                # Trace-derived candidates need current identity checks before they can be sampled.
                if actor == 3: raise ValueError('Wrong vtable')
                if actor == 4: raise OSError('Actor freed')
                return None, {'owner_like': '0x22' if actor == 2 else '0x11'}
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'events.jsonl'
            header = dict(kind='session', **Game.identity)
            events = [dict(kind='action_call', actor=hex(a), owner='0x11', valid_fields=1) for a in range(1,5)]
            path.write_text('\n'.join(map(json.dumps, [header, *events])) + '\n{"kind":', encoding='utf8')
            found = encounter.runtime_candidates(Game(), path)
            self.assertEqual([c['object'] for c in found['candidates']], ['0x1'])
            header['process_started'] += 1
            path.write_text('\n'.join(map(json.dumps, [header, *events])) + '\n', encoding='utf8')
            self.assertIsNone(encounter.runtime_candidates(Game(), path))

    def test_runtime_discovery_waits_for_header_and_obeys_cancellation(self):
        # Wait for an active trace header while still honoring capture cancellation.
        # Read a partial first trace header, then request cancellation.
        # Discovery must wait for complete identity evidence while still responding to Stop.
        class Game:
            identity = {'pid': 12}
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'events.jsonl'
            path.write_text('{"pid":12', encoding='utf8')
            self.assertIsNone(encounter.runtime_candidates(Game(), path))
            with self.assertRaises(InterruptedError):
                encounter.runtime_candidates(Game(), path, lambda: (
                    # Request immediate cancellation while probing a partial trace header.
                    # Return true on the first stop check.
                    # Discovery must honor Stop before waiting for more recording data.
                    True
                ))

    def backend(self, event, out_calls, first_error=False):
        # Provide a repeatable recorder backend that ends after two retained takes.
        # Simulate optional process absence and selected-actor retirement without game access.
        # Supervisor recovery must preserve take numbering and evidence across retries.
        class Game:
            def __enter__(self):
                # Enter the recorder's fake process context.
                # Return an object with no process handle or game-memory capability.
                # Recovery tests must use the normal context protocol without attaching to Nioh.
                return self
            def __exit__(self, *exc):
                # Release the recorder fixture without suppressing exceptions.
                # Own no external handle, so no disposal action is required.
                # Programming errors must propagate through the supervisor's error-reporting path.
                pass
        count = [0]
        def pid():
            # Return a distinct fixture process identity on each discovery attempt.
            # Optionally fail only the first attempt as a missing game process.
            # The supervisor must recover environmental absence without overwriting prior takes.
            count[0] += 1
            if first_error and count[0] == 1:
                raise ValueError('No game process')
            return count[0]
        def record(game, cfg, folder, *args, **kwargs):
            # Write a complete fixture take and request actor rediscovery.
            # Set the caller's stop event after the second retained folder is created.
            # Retry tests must terminate deterministically while preserving both raw recordings.
            out_calls.append(folder)
            folder.mkdir()
            (folder / 'events.jsonl').write_text(json.dumps({'kind': 'session'}) + '\n' +
                json.dumps(state(0.1)) + '\n' + json.dumps({'kind': 'end'}), encoding='utf8')
            if len(out_calls) == 2:
                event.set()
            return {'stop_reason': 'selected_actor_invalid_rediscovery_required'}
        return {'open': lambda pid: (
            # Open a handle-free fake process for the supervisor retry fixture.
            # Ignore the synthetic PID and return its context-managed Game object.
            # Retained-take tests must never attach to an actual game process.
            Game()
        ), 'pid': pid, 'discover': lambda *a, **k: (
            # Return an empty discovery result for the fixed-role retry fixture.
            # Leave actor selection to the independent select callback.
            # Process and take-lifetime behavior can be isolated from memory scanning.
            {}
        ),
                'select': lambda *a: (
                    # Select stable fixture player and boss identities for each retry.
                    # Return actor ids one and two without native address discovery.
                    # The supervisor test exercises take preservation after reported actor retirement.
                    (1, 2)
                ), 'record': record}

    def test_recovers_process_and_actor_loss_retaining_separate_takes(self):
        # Recover process and actor loss into separate retained takes.
        # Fail initial process discovery and retire selected actors after subsequent short takes.
        # Automatic retries must retain separate evidence folders and expose the waiting reason.
        stop, calls, statuses = threading.Event(), [], []
        with tempfile.TemporaryDirectory() as td:
            status = encounter.record_encounter('okatsu', td, stop_event=stop, retry_seconds=0.05,
                status_callback=statuses.append, backend=self.backend(stop, calls, first_error=True))
            index = json.loads((Path(td) / 'reconstruction.json').read_text())
            self.assertEqual(len(index['segments']), 2)
            self.assertNotEqual(calls[0], calls[1])
            self.assertEqual(status['state'], 'stopped')
            self.assertTrue(any(s.get('detail') == 'No game process' for s in statuses))

    def test_resume_after_interruption_keeps_original_capture_and_new_take_number(self):
        # Resume interrupted recording without overwriting earlier evidence or take numbers.
        # Resume a folder containing an interrupted first take and an existing recording id.
        # New attempts must increment take numbers without rewriting raw evidence or identity.
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            manifest = {'boss_id': 'okatsu', 'signature': encounter.DEFAULT_SIGNATURES['okatsu'],
                        'recording_id': 'old', 'identity_basis': 'test'}
            (folder / 'encounter.json').write_text(json.dumps(manifest))
            take = folder / 'take-0001'
            take.mkdir()
            original = json.dumps(state(0.1)) + '\n{"unfinished":'
            (take / 'events.jsonl').write_text(original)
            stop, calls = threading.Event(), []
            encounter.record_encounter('okatsu', folder, stop_event=stop, retry_seconds=0.05,
                                       backend=self.backend(stop, calls))
            self.assertEqual((take / 'events.jsonl').read_text(), original)
            self.assertEqual(calls[0].name, 'take-0002')
            self.assertEqual(json.loads((folder / 'encounter.json').read_text())['recording_id'], 'old')

    def test_existing_stop_file_attaches_to_nothing(self):
        # Honor an existing Stop file before attaching to any process.
        # Create the encounter Stop file before invoking the supervisor with no backend.
        # Cancellation must finish with zero takes before any process attachment is possible.
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / 'STOP').touch()
            status = encounter.record_encounter('okatsu', td, backend={})
            self.assertEqual(status['takes'], 0)
            self.assertEqual(status['state'], 'stopped')

    def test_mismatching_resume_identity_is_rejected_without_touching_evidence(self):
        # Reject incompatible resume identity without modifying saved evidence.
        # Resume a folder whose manifest names another boss and signature.
        # The recorder must refuse the mismatch and leave the original manifest byte-for-byte intact.
        with tempfile.TemporaryDirectory() as td:
            manifest = Path(td) / 'encounter.json'
            original = json.dumps({'boss_id': 'another_boss', 'signature': []})
            manifest.write_text(original)
            with self.assertRaisesRegex(ValueError, 'different boss'):
                encounter.record_encounter('okatsu', td, backend={})
            self.assertEqual(manifest.read_text(), original)

    def test_concurrent_recorder_cannot_overwrite_manifest(self):
        # Prevent a second recorder from overwriting an active encounter manifest.
        # Hold the encounter lock through a second recorder invocation.
        # Exclusive ownership must be checked before creating or replacing capture metadata.
        import msvcrt
        with tempfile.TemporaryDirectory() as td:
            lock = (Path(td) / 'recorder.lock').open('w+b')
            try:
                lock.write(b'0')
                lock.flush()
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                with self.assertRaisesRegex(ValueError, 'already being recorded'):
                    encounter.record_encounter('okatsu', td, backend={})
                self.assertFalse((Path(td) / 'encounter.json').exists())
            finally:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                lock.close()


class CatalogueIntegrationTests(unittest.TestCase):
    def test_descriptor_free_capture_stays_outside_sword_catalogue(self):
        # Retain descriptor-free observations in raw recording output only.
        # Reconstruct their evidence and try reimporting it into the curated catalogue.
        # Missing source identity cannot repopulate the removed observation ledger.
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'catalogue'))
        from catalogue import load_catalogue, merge_reconstruction
        original = load_catalogue()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'events.jsonl'
            path.write_text(json.dumps(state(.1, descriptor=None)), encoding='utf8')
            recorded = encounter.reconstruct_capture(path, 'okatsu')
            self.assertEqual(len(recorded['unclassified_observations']), 1)
            merged = merge_reconstruction(original, recorded)
            self.assertEqual(merged, merge_reconstruction(merged, recorded))
            self.assertEqual(merged['moves'], original['moves'])
            self.assertEqual(merged, original)

    def test_source_semantics_survive_import_without_promoting_a_move(self):
        # Retain source semantics without treating a captured move as implemented.
        # Encode source flags, Ki cost, recovery and a transition target in captured bytes.
        # The raw reconstruction retains decoded facts while catalogue enrichment skips unknown moves.
        from catalogue import load_catalogue, merge_reconstruction
        original = load_catalogue()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'events.jsonl'
            event = metadata(action=0xF001, motion=4100)
            payload = bytearray.fromhex(event['payload_prefix']['bytes'])
            struct.pack_into('<hQ', payload, 0x16, 10, 0x194C0000)
            struct.pack_into('<h', payload, 0x24, 22)
            event['payload_prefix']['bytes'] = payload.hex()
            event['transition_entries'] = [{'target_key_0x14_i16': 0xF002}]
            path.write_text('\n'.join(map(json.dumps, [state(0.1, 0xF001), event])), encoding='utf8')
            recorded = encounter.reconstruct_capture(path, 'jin_hayabusa')
            merged = merge_reconstruction(original, recorded)
        move = next(m for m in recorded['actions'] if m['source']['action_id'] == 0xF001)
        self.assertEqual(move['source']['flags'], 0x194C0000)
        self.assertEqual(move['source']['ki_cost'], 10)
        self.assertEqual(move['source']['recovery_frame'], 22)
        self.assertEqual(move['source']['transition_targets'], [0xF002])
        self.assertEqual(move['observations'], 1)
        self.assertEqual(merged, original)
        self.assertEqual(merged, merge_reconstruction(merged, recorded))

    def test_segmented_recording_import_is_idempotent_and_preserves_working_moves(self):
        # Merge segmented encounters idempotently while preserving the working baseline.
        # Import an encounter index containing two reconstructed takes twice.
        # Captured discoveries must not overwrite curated names, baseline bindings or implementation status.
        root = Path(__file__).resolve().parents[2]
        sys.path.insert(0, str(root / 'catalogue'))
        from catalogue import load_catalogue, save_catalogue, merge_recording
        original = load_catalogue()
        baseline = {move['id']: move for move in original['moves'] if move['implementation']['selectable']}
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            catalogue = folder / 'moves.xlsx'
            save_catalogue(catalogue, original)
            (folder / 'encounter.json').write_text(json.dumps({'boss_id': 'okatsu', 'recording_id': 'integration'}))
            for number in (1, 2):
                take = folder / f'take-{number:04d}'
                take.mkdir()
                events = [{'kind': 'session'}, state(0.1), metadata(), state(0.2, 0xCA0),
                          metadata(action=0xCA0, motion=1500, t=0.25), {'kind': 'end'}]
                (take / 'events.jsonl').write_text('\n'.join(map(json.dumps, events)), encoding='utf8')
            index = encounter.reconstruct_encounter(folder)
            self.assertEqual(index['segments'][0]['path'], 'take-0001/reconstruction.json')
            merged = merge_recording(catalogue, folder / 'reconstruction.json')
            again = merge_recording(catalogue, folder / 'reconstruction.json')
            self.assertEqual(merged, again)
            self.assertFalse(any(move['source'].get('action_id') == 0xCA0 for move in merged['moves']))
            for move in merged['moves']:
                if move['id'] in baseline:
                    self.assertEqual(move['name'], baseline[move['id']]['name'])
                    self.assertEqual(move['implementation'], baseline[move['id']]['implementation'])
                    self.assertEqual(move['default_binding'], baseline[move['id']]['default_binding'])


