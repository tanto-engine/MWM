import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
MOD_ROOT = ROOT.parent/'tanto-sword-mod'
sys.path.insert(0,str(ROOT))
from catalogue import iter_moves, load_catalogue, save_catalogue, validate_catalogue, merge_reconstruction, merge_recording, rename_move


class CatalogueTests(unittest.TestCase):
    def test_sword_strings_keep_distinct_source_identity_and_exclude_trial_choices(self):
        # Preserve each distinct sword string once while keeping ordered action evidence.
        # Inspect nested constituent identities and the retained sword import topology.
        # Non-sword trials and constituent heavy attacks cannot remain standalone choices.
        records = list(iter_moves(self.catalogue))
        self.assertEqual((len(self.catalogue['moves']), len(records)), (14, 39))
        self.assertEqual({move['weapon'] for move in records}, {'sword'})
        groups = {move['id']: move for move in self.catalogue['moves']}
        for key, actions in ((0xBC0, [0xBC0,0xC6C,0xC6D]), (0xC6E, [0xC6E,0xC6F,0xC70]), (0xC75,[0xC75,0xC77,0xC78])):
            group = groups[f'jin_hayabusa.action_{key:04x}']
            self.assertEqual([move['source']['action_id'] for move in iter_moves({'moves':[group]})], actions)
        for key in (0xC6C,0xC6D,0xCA9,0xCAC,0xCAD,0xC7B,0xC7C,0xC7F,0xC6B,0xCAE):
            self.assertNotIn(f'jin_hayabusa.action_{key:04x}', groups)
        manifest = json.loads((MOD_ROOT/'data/imports/jin_hayabusa.json').read_text())
        self.assertEqual(len(manifest['moves']), 28)
        self.assertEqual(set(manifest['hold_chains']), {'jin_hayabusa.action_0bbf','jin_hayabusa.action_0c79','jin_hayabusa.action_0c75',
                                                       'jin_hayabusa.izuna_drop','jin_hayabusa.action_0c71','jin_hayabusa.action_0c81'})

    def test_filtered_encounters_keep_hashes_lines_and_sequence_boundaries(self):
        # Make derived sword evidence traceable after mixed capture rows are removed.
        # Verify its byte hashes, canonical fingerprint and every retained event reference.
        # Filtered sequences must never connect two actions through a removed observation.
        import hashlib
        for encounter in self.catalogue['encounters']:
            record = json.loads((ROOT/encounter['path']).read_text())
            source = ROOT/record['source']['path']
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), encounter['source_sha256'])
            self.assertEqual(record['source']['sha256'], encounter['source_sha256'])
            self.assertEqual(hashlib.sha256(json.dumps(record,sort_keys=True,separators=(',',':')).encode()).hexdigest(), encounter['sha256'])
            identities = {action['id'] for action in record['actions']}
            self.assertTrue(all(set(string['actions']) <= identities for string in record['strings']))
            lines = source.read_text().splitlines()
            for action in record['actions']:
                for evidence in action['evidence']:
                    event = json.loads(lines[evidence['line']-1])
                    observed = event.get('after_key', event.get('action_key_u32',event.get('descriptor',{}).get('action_key_u32')))
                    if observed is None:
                        self.assertEqual(event['descriptor']['word0_u16'], action['source']['action_id'] & 0xffff)
                    else:
                        self.assertEqual(observed, action['source']['action_id'])

    def test_nested_reimport_updates_constituent_without_creating_standalone_choice(self):
        # Resolve an imported source identity inside its owning string.
        # Replay a known constituent and reject duplicate identities anywhere in the tree.
        # Evidence enrichment must not reintroduce standalone string attacks.
        source = self.reconstruction(0xC62,0xC62)
        source['actions'][0]['source'].update(motion_id=1211,timing_id=1211)
        merged = merge_reconstruction(self.catalogue,source,'capture.json')
        self.assertEqual(len(merged['moves']),len(self.catalogue['moves']))
        self.assertEqual(sum(move['id']=='okatsu.action_0c62' for move in iter_moves(merged)),1)
        merged['moves'].append(copy.deepcopy(next(move for move in iter_moves(merged) if move['id']=='okatsu.action_0c62')))
        with self.assertRaisesRegex(ValueError,'duplicate move ID'):
            validate_catalogue(merged)

    def setUp(self):
        # Load the maintained catalogue for each mutation-isolation test.
        # Create a fresh object from disk instead of sharing prior test changes.
        # Baseline bindings and curated evidence must survive imports independently.
        self.catalogue=load_catalogue()

    def reconstruction(self, action_id=0xC99, word=0xC99):
        # Represent a partial boss capture with one observed temporal successor.
        # Allow the full action identity to be absent while retaining the observed low word.
        # Import must preserve unknown evidence without promoting it into playable configuration.
        identity=f'boss-1/action:{action_id:08X}' if action_id is not None else f'boss-1/word0:{word:04X}'
        return {'schema_version':1,'kind':'encounter_reconstruction','boss_id':'okatsu','complete':False,'issues':['interrupted'],
                'actions':[{'id':identity,'actor_label':'boss-1','role':'boss_candidate','source':{'action_id':action_id,'observed_word0_u16':word,'motion_id':999,'timing_id':999,'timing_override':-1},'observations':2,'evidence':[{'path':'take/events.jsonl','line':2,'t':.2}]}],
                'observed_successors':[{'actor_label':'boss-1','from':identity,'to':'boss-1/action:00000C64','count':1,'evidence':[{'path':'take/events.jsonl','line':3,'t':.3}],'relationship':'sampled_temporal_order'}],
                'strings':[],'unclassified_observations':[]}

    def test_baseline_preserved(self):
        # Preserve the confirmed Okatsu baseline during catalogue loading.
        # Load the canonical Okatsu rows and inspect source identities and tap/hold settings.
        # Catalogue maintenance must preserve the already playable baseline configuration.
        moves={m['id']:m for m in self.catalogue['moves']}
        tap=moves['okatsu.charged_rush']; hold=moves['okatsu.leaping_slash']
        self.assertEqual((tap['source']['action_id'],tap['source']['motion_id']),(0xC64,1220))
        self.assertEqual((hold['source']['action_id'],hold['source']['motion_id']),(0xC66,1230))
        self.assertEqual(tap['default_binding'],{'chord':['Native Tiger Sprint'],'gesture':'native_skill','weapon':'sword','replaces_action_id':0xFAA})
        self.assertIsNone(hold['default_binding'])
        jump=moves['jin_hayabusa.flying_swallow_jump']
        self.assertEqual(jump['source']['action_id'],0xC71)
        self.assertIsNone(jump['default_binding'])
        self.assertTrue(tap['implementation']['selectable'])
        self.assertTrue(hold['implementation']['selectable'])

    def test_mixed_capture_cannot_repopulate_excluded_moves_or_player_ledger(self):
        # Keep excluded identities out when an original mixed capture is reimported.
        # Include a known non-sword Jin action, an unknown boss and unrelated player states.
        # Only already curated sword source identities may enrich this catalogue.
        before=copy.deepcopy(self.catalogue)
        record=self.reconstruction(0xCA9,0xCA9)
        record['boss_id']='jin_hayabusa'
        record['actions'] += [dict(record['actions'][0],role='player_candidate'),dict(record['actions'][0],role='unassigned')]
        self.assertEqual(merge_reconstruction(self.catalogue,record,'capture.json'),before)
        record['boss_id']='unknown_boss'
        self.assertEqual(merge_reconstruction(self.catalogue,record,'capture.json'),before)
        self.assertEqual(self.catalogue,before)

    def test_repeat_import_is_idempotent(self):
        # Make repeated imports preserve one copy of each captured fact.
        # Merge the same reconstruction twice.
        # Evidence deduplication must prevent repeated imports from multiplying catalogue facts.
        record=self.reconstruction(0xC66,0xC66)
        record['actions'][0]['source'].update(motion_id=1230,timing_id=1230)
        first=merge_reconstruction(self.catalogue,record,'capture.json')
        self.assertEqual(first,merge_reconstruction(first,record,'capture.json'))

    def test_metadata_upgrade_does_not_count_the_capture_twice(self):
        # Decode more facts from one retained capture without manufacturing another encounter.
        # Keep its raw source hash stable while adding a newly understood cancel boundary.
        # Observation counts, unassigned evidence and curated bindings must remain unchanged.
        record=self.reconstruction(0xC66,0xC66)
        record['actions'][0]['source'].update(motion_id=1230,timing_id=1230)
        record['source']={'sha256':'a'*64}
        first=merge_reconstruction(self.catalogue,record,'capture.json')
        record['actions'][0]['source']['cancel_frame']=60
        record['actions'][0]['source']['transition_rows_total']=75
        second=merge_reconstruction(first,record,'capture.json')
        self.assertEqual(len(first['encounters']),len(second['encounters']))
        move=next(m for m in second['moves'] if m['id']=='okatsu.leaping_slash')
        original=next(m for m in self.catalogue['moves'] if m['id']==move['id'])
        self.assertEqual(move['capture']['state_events'],original['capture'].get('state_events',0)+2)
        self.assertEqual(move['source']['cancel_frame'],60)
        self.assertEqual(move['source']['transition_rows_total'],75)
        self.assertEqual(first['observations'],second['observations'])
        self.assertEqual(second,merge_reconstruction(second,record,'capture.json'))

    def test_existing_curated_configuration_survives(self):
        # Keep curated names, bindings and adaptation through later imports.
        # Import observations for an already curated move.
        # Recorded source evidence must not overwrite its name, binding or implementation decisions.
        baseline=copy.deepcopy(self.catalogue['moves'][0])
        record=self.reconstruction(0xC64,0xC64)
        result=merge_reconstruction(self.catalogue,record,'capture.json')['moves'][0]
        for key in ('id','name','category','source','default_binding','implementation','verification','adaptation','limitations'):
            self.assertEqual(result[key],baseline[key],key)
        self.assertEqual(result['source_conflicts'][0]['fields']['motion_id'],{'catalogue':1220,'observed':999})

    def test_word_only_capture_cannot_claim_full_action_id(self):
        # Prevent a low-word-only capture from claiming a known full action identity.
        # Merge a capture retaining only the descriptor's low action word.
        # An unresolved 16-bit observation cannot become a verified 32-bit action identity.
        record=self.reconstruction(None,0xC64)
        result=merge_reconstruction(self.catalogue,record)
        self.assertEqual(len(result['moves']),len(self.catalogue['moves']))
        observed=result['observations'][-1]
        self.assertEqual(observed['status'],'word0_only')
        self.assertIsNone(observed['source']['action_id'])
        self.assertIn('okatsu.charged_rush',observed['candidate_move_ids'])

    def test_unassigned_actor_not_treated_as_boss(self):
        # Keep unassigned actor observations separate from boss move ownership.
        # Change the reconstructed actor's role from identified boss to unassigned.
        # Encounter context alone must not authorize a permanent boss-move association.
        record=self.reconstruction()
        record['actions'][0]['role']='unassigned'
        record['actions'][0]['actor_label']='boss'
        result=merge_reconstruction(self.catalogue,record)
        self.assertEqual(len(result['moves']),len(self.catalogue['moves']))
        self.assertEqual(result['observations'],self.catalogue['observations'])

    def test_duplicate_and_transient_fields_rejected(self):
        # Reject duplicate move identities and transient runtime fields.
        # Introduce duplicate permanent identities and session-specific pointer fields.
        # Catalogue validation must reject ambiguous records and addresses that expire after reload.
        for mutation in ('duplicate','pointer'):
            invalid=copy.deepcopy(self.catalogue)
            if mutation=='duplicate': invalid['moves'].append(copy.deepcopy(invalid['moves'][0]))
            else: invalid['moves'][0]['source']['address']='0x123456'
            with self.assertRaises(ValueError): validate_catalogue(invalid)

    def test_index_import_and_rename_preserve_status(self):
        # Keep implementation status unchanged when importing or renaming entries.
        # Import an indexed capture and rename its move through the maintained catalogue API.
        # Editorial naming must retain implementation status and evidence rather than resetting progress.
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            target=folder/'moves.xlsx'; save_catalogue(target, self.catalogue)
            take=folder/'take-0001';take.mkdir()
            (take/'reconstruction.json').write_text(json.dumps(self.reconstruction(0xC64,0xC64)),encoding='utf8')
            index=folder/'reconstruction.json';index.write_text(json.dumps({'schema_version':1,'kind':'encounter_index','segments':[{'path':'take-0001/reconstruction.json'}]}),encoding='utf8')
            merge_recording(target,index)
            renamed=rename_move(target,'okatsu.charged_rush','New descriptive name','sword_attack')
            move=next(m for m in renamed['moves'] if m['id']=='okatsu.charged_rush')
            self.assertEqual(move['name'],'New descriptive name')
            self.assertEqual(move['implementation'],self.catalogue['moves'][0]['implementation'])
            self.assertEqual(load_catalogue(target),renamed)


