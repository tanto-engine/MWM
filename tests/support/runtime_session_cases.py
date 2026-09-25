import copy
import ctypes as C
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'runtime'))
import native_loader as loader
from runtime_session import encode_session, POINTER_FIELDS, SESSION_CONFIG, MOVE_IMPORT, MOVE_ADAPTER, MAGIC, VERSION
from move_imports import read_import_manifest, check_import_topology
from session_fixture import BOSS


class RuntimeSessionTests(unittest.TestCase):
    def setUp(self):
        # Copy the complete session fixture with a fixed configuration tag.
        # Retain its process id and creation time as separate expected identities.
        # Encoding must bind addresses to one process birth rather than PID alone.
        self.config = copy.deepcopy(BOSS)
        self.config['config_tag'] = '123456789abcdef0'
        self.pid = self.config['session']['pid']
        self.born = int(self.config['session']['creation_filetime'])

    def test_pointer_order_matches_native_abi(self):
        # Keep Python session packing identical to the native ABI field order.
        # Encode a complete session and unpack its fixed header and pointer sequence.
        # Version seven places the stance mask, Frost slots, window and startup speed before resource pointers.
        values = SESSION_CONFIG.unpack(encode_session(self.config, self.pid, self.born))
        self.assertEqual(values[:16], (MAGIC, 7, 4168, self.pid, self.born,
                                      0x123456789abcdef0, 0, 0, 0, 0, 0, 0, 0, 0, 750, 8))
        self.assertEqual(values[16:42], tuple(self.config[key] for key in POINTER_FIELDS)
                         + tuple(self.config['originals']))
        self.assertEqual(values[42:44], (7,2))
        encoded = encode_session(self.config, self.pid, self.born)
        move = MOVE_IMPORT.unpack_from(encoded,328+2*96)
        self.assertEqual(move[4:13], (0x184C0000,0xC61,1210,52,14,3,30,45,1))
        self.assertEqual(move[13:16], (22,12,0x297D2215))
        self.assertEqual(encoded[328+7*96:2632], bytes(17*96))
        self.assertEqual(encoded[2632:], bytes(24*64))
        grapple = dict(self.config, native_grapple=True)
        enabled = encode_session(grapple, self.pid, self.born)
        self.assertEqual(SESSION_CONFIG.unpack(enabled)[9], 1)
        self.assertEqual(enabled[64:], encoded[64:])
        for value in (1, None, 'true'):
            with self.subTest(grapple=value), self.assertRaisesRegex(ValueError, 'must be a boolean'):
                encode_session(dict(self.config, native_grapple=value), self.pid, self.born)
        header = (ROOT / 'runtime/native/boss_session_schema.h').read_text()
        import re
        self.assertEqual(re.findall(r'^    uint64_t (\w+);$', header, re.MULTILINE), list(POINTER_FIELDS))

    def test_rejects_mismatched_process_and_invalid_pointer_types(self):
        # Reject process-identity mismatches and invalid pointer types.
        # Change process birth and supply invalid address values during session encoding.
        # The ABI must bind transient pointers to one verified process identity.
        for pid, born in ((self.pid + 1, self.born), (self.pid, self.born + 1)):
            with self.assertRaises(ValueError):
                encode_session(self.config, pid, born)
        for value in (None, True, '0x12345', 0, 0xffffffffffffffff):
            config = copy.deepcopy(self.config); config['player'] = value
            with self.assertRaises(ValueError):
                encode_session(config, self.pid, self.born)

    def test_jin_adapters_preserve_baseline_and_reject_wrong_player_mapping(self):
        # Append the recorded D candidate with three independent William replacement descriptors.
        # Inspect the exact adapter ABI offset, then corrupt pointer, mapping and source-family fields.
        # A valid Jin table must preserve every Okatsu slot and cannot redirect another player action.
        manifest = read_import_manifest(ROOT/'catalogue/imports/jin_hayabusa.json')
        selected = {move['id']: move for move in manifest['moves']}
        for index, identifier in enumerate(manifest['candidates']['D']):
            move = copy.deepcopy(selected[identifier])
            move.update(descriptor=0x510000+index*0x1000, payload=0x610000+index*0x1000,
                        clip=0x710000+index*0x1000, timing_record=0x810000+index*0x1000)
            self.config['imports'].append(move)
            self.config['adapters'].append(dict(action_resource=0x910000, timing_resource=0x920000,
                bank=0x930000, motion_bank=0x940000, timing_wrapper=0x950000,
                player_descriptor=0xA10000+index*0x1000,kind=1, **move['replacement']))
        encoded = encode_session(self.config, self.pid, self.born)
        self.assertEqual(encoded[2632:2632+7*64], bytes(7*64))
        self.assertEqual(MOVE_ADAPTER.unpack_from(encoded,2632+7*64),
            (0x910000,0x920000,0x930000,0x940000,0x950000,0xA10000,0xCF5,4300,46,38,1))
        self.assertEqual(encoded[2632+10*64:], bytes(14*64))
        for field,value in (('player_descriptor',0),('player_key',0xCF4),('transition_count',65),('recovery_frame',0)):
            config=copy.deepcopy(self.config);config['adapters'][7][field]=value
            with self.subTest(field=field), self.assertRaises(ValueError):
                encode_session(config,self.pid,self.born)
        config=copy.deepcopy(self.config);config['adapters'][7]=None
        with self.assertRaisesRegex(ValueError,'missing its native adapter'):
            encode_session(config,self.pid,self.born)
        config=copy.deepcopy(self.config);config['adapters'][7].update(config['imports'][8]['replacement'])
        with self.assertRaisesRegex(ValueError,'manifest mapping'):
            encode_session(config,self.pid,self.born)
        config=copy.deepcopy(self.config);config['imports'][7]['next_variant']=8
        with self.assertRaisesRegex(ValueError,'native player transitions'):
            encode_session(config,self.pid,self.born)

    def test_manifest_topology_and_source_family_reject_unsupported_imports(self):
        # Reject malformed import topology and unsupported source action families.
        # Introduce duplicate keys, unsupported families, bad indices and chain cycles.
        # Configuration-only imports must not bypass capability or topology constraints.
        manifest = read_import_manifest(ROOT/'catalogue/imports/okatsu.json')
        self.assertEqual([move['next_variant'] for move in manifest['moves']], [-1,-1,3,4,5,6,-1])
        cases = [(2,'next_variant',16), (2,'next_variant',2), (4,'next_variant',2),
                 (2,'next_start',46), (4,'next_end',9), (2,'key',0xC64),
                 (2,'transition_count',29), (2,'recovery_frame',-1)]
        for index, field, value in cases:
            with self.subTest(field=field,value=value):
                config = copy.deepcopy(self.config)
                config['imports'][index][field] = value
                if index == 4 and field == 'next_variant':
                    config['imports'][index].update(next_start=1,next_end=2)
                with self.assertRaises(ValueError):
                    encode_session(config,self.pid,self.born)
        for field, value in (('index',512),('frame',65536),('hash',0)):
            config=copy.deepcopy(self.config); config['imports'][2]['voices'][0][field]=value
            with self.assertRaises(ValueError):
                encode_session(config,self.pid,self.born)
        for field in ('descriptor','payload','clip','timing_record'):
            config=copy.deepcopy(self.config); config['imports'][0][field]+=8
            with self.assertRaisesRegex(ValueError,'legacy session'):
                encode_session(config,self.pid,self.born)
        for value in (-1,7,True,6):
            with self.assertRaises(ValueError):
                check_import_topology(self.config['imports'],value)
        raw=json.loads((ROOT/'catalogue/imports/okatsu.json').read_text())
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'imports.json'
            for change in ({'string_entry':'absent'},{'string_entry':'okatsu.action_0361'}):
                path.write_text(json.dumps(dict(raw,**change)))
                with self.assertRaises(ValueError): read_import_manifest(path)
            bad=copy.deepcopy(raw);bad['moves'][2]['flags']=0xFFFFFFFF;path.write_text(json.dumps(bad))
            with self.assertRaises(ValueError): read_import_manifest(path)
            bad=copy.deepcopy(raw);bad['moves'][2]['next']='absent';path.write_text(json.dumps(bad))
            with self.assertRaises(ValueError): read_import_manifest(path)

    def test_only_camera_original_may_be_null(self):
        # Allow a null original camera slot while requiring every other resource pointer.
        # Set each session pointer to zero in turn while preserving a null original camera slot.
        # Only the researched optional slot may be null; required ownership pointers remain mandatory.
        self.config['camera_original'] = 0
        values = SESSION_CONFIG.unpack(encode_session(self.config,self.pid,self.born))
        self.assertEqual(values[16+POINTER_FIELDS.index('camera_original')],0)
        for field in POINTER_FIELDS:
            if field == 'camera_original':
                continue
            with self.subTest(field=field):
                config=copy.deepcopy(self.config);config[field]=0
                with self.assertRaises(ValueError):encode_session(config,self.pid,self.born)
        for index in range(4):
            config=copy.deepcopy(self.config);config['originals'][index]=0
            with self.subTest(original=index), self.assertRaises(ValueError):
                encode_session(config,self.pid,self.born)

        for field in ('descriptor','payload','clip','timing_record'):
            config=copy.deepcopy(self.config);config['imports'][2][field]=0
            with self.subTest(import_pointer=field), self.assertRaises(ValueError):
                encode_session(config,self.pid,self.born)

    def test_sword_preset_expands_only_selected_stance_dependencies(self):
        # Resolve grouped sword strings and standalone holds through the same preset validator.
        # Rotate native stance ownership, disable taps independently, and reject duplicate holds.
        # Unselected and non-sword research must never enter a prepared runtime table.
        import prepare_session as prepare
        from engine_config import DEFAULT_PRESET
        settings=copy.deepcopy(DEFAULT_PRESET)
        manifest=prepare.configured_replacements(settings)
        self.assertEqual([move['key'] for move in manifest['moves']], [0xC6E,0xC6F,0xC70,0xC79,0xC79,0xC7A,0x3B2,0x3B4,0x3B6,0xCAC,0xCAD])
        self.assertEqual((manifest['hold_stances'],manifest['frost_variants'],manifest['frost_milliseconds']), (1,[0,5,10],750))
        settings['frost_moon']=dict(low=None,mid=None,high=None)
        manifest=prepare.configured_replacements(settings)
        self.assertEqual([move['key'] for move in manifest['moves']], [0xC6E,0xC6F,0xC70,0xC79])
        self.assertEqual((manifest['hold_variant'],manifest['hold_milliseconds']), (4,250))
        settings['stance_holds']['high']='jin_hayabusa.action_0cac'
        manifest=prepare.configured_replacements(settings)
        self.assertEqual([move['key'] for move in manifest['moves']], [0xC6E,0xC6F,0xC70,0xC79,0xCAC,0xCAD])
        for index,source in enumerate(manifest['moves'],7):
            move=copy.deepcopy(source)
            move.update(descriptor=0x510000+index*0x1000,payload=0x610000+index*0x1000,
                        clip=0x710000+index*0x1000,timing_record=0x810000+index*0x1000)
            adapter=dict(action_resource=0x910000,timing_resource=0x920000,bank=0x930000,
                         motion_bank=0x940000,timing_wrapper=0x950000,kind=move['adapter_kind'],
                         player_descriptor=0xA00000+move['replacement']['player_key']*0x100,**move['replacement'])
            self.config['imports'].append(move); self.config['adapters'].append(adapter)
        self.config.update(hold_variant=11,hold_milliseconds=250,hold_camera_bank=0)
        self.assertEqual(len(encode_session(self.config,self.pid,self.born)),SESSION_CONFIG.size)
        frost=dict(self.config,hold_stances=1,frost_variants=[0,0,12],frost_milliseconds=750,frost_speed=8)
        self.assertEqual(SESSION_CONFIG.unpack(encode_session(frost,self.pid,self.born))[10:16], (1,0,0,12,750,8))
        for field,values in (('hold_stances',(-1,8,True)),('frost_milliseconds',(99,1501,True,750.0)),
                             ('frost_speed',(0,9,True,8.0)),
                             ('frost_variants',([12,0,0],[0,0,11],[0,0,13],[0,0,14],[0,0,True],[0,0],None))):
            for value in values:
                with self.subTest(field=field,value=value), self.assertRaises(ValueError):
                    encode_session(dict(frost,**{field:value}),self.pid,self.born)
        for field in ('bank','player_descriptor'):
            bad=copy.deepcopy(self.config); bad['adapters'][12][field]+=0x1000
            with self.assertRaisesRegex(ValueError,'matching held-entry owner'):
                encode_session(bad,self.pid,self.born)
        settings['stance_holds']['mid']=settings['stance_holds']['high']
        with self.assertRaisesRegex(ValueError,'duplicate imports'):
            prepare.configured_replacements(settings)
        settings['stance_holds']=dict(low=None,mid='jin_hayabusa.action_0c79',high=None)
        settings['low_heavy']=None
        held=prepare.configured_replacements(settings)
        self.assertEqual([move['key'] for move in held['moves']],[0xC79])
        self.assertEqual(held['moves'][0]['replacement']['player_key'],0xCB7)
        settings['stance_holds']['mid']=None
        self.assertIsNone(prepare.configured_replacements(settings))
        for key in ('jin_hayabusa.action_0ca9','jin_hayabusa.action_0c6c','jin_hayabusa.action_0cae'):
            settings['stance_holds']['low']=key
            with self.assertRaisesRegex(ValueError,'standalone sword move'):
                prepare.configured_replacements(settings)

    def test_izuna_alias_preserves_low_launcher_and_rejects_other_duplicate_sources(self):
        # Separate the mid native-contact chain from the low standalone launcher.
        # Corrupt duplicate identity, stance, source bytes and the exact zero-flag bridge independently.
        # A shared animation cannot authorize another source family or a forced paired entry.
        import prepare_session as prepare
        from engine_config import DEFAULT_PRESET
        settings=copy.deepcopy(DEFAULT_PRESET)
        manifest=prepare.configured_replacements(settings)
        moves=manifest['moves']; low,izuna,bridge=moves[3:6]
        check_import_topology(moves,None)
        self.assertNotIn('native_followups',low)
        self.assertEqual((low['next_variant'],low['replacement']['player_key']),(-1,0xCF5))
        self.assertEqual((izuna['next_variant'],izuna['replacement']['player_key']),(-1,0xCB7))
        self.assertEqual(izuna['native_followups'],[bridge['id']])
        self.assertEqual((bridge['next_variant'],bridge['next_start'],bridge['next_end']),(6,0,0))
        for source in moves:
            move=copy.deepcopy(source); address=0x500000+move['key']*0x1000
            move.update(descriptor=address,payload=address+0x100,clip=address+0x200,timing_record=address+0x300)
            if move['next_variant']>=0:move['next_variant']+=7
            adapter=dict(action_resource=0x910000,timing_resource=0x920000,bank=0x930000,
                         motion_bank=0x940000,timing_wrapper=0x950000,kind=move['adapter_kind'])
            if adapter['kind']==3:
                adapter.update(player_descriptor=0,player_key=0,player_motion=0,transition_count=0,recovery_frame=0)
            else:
                adapter.update(player_descriptor=0xA00000+move['replacement']['player_key']*0x100,**move['replacement'])
            self.config['imports'].append(move);self.config['adapters'].append(adapter)
        self.config.update(hold_variant=11,hold_milliseconds=250,hold_camera_bank=0x960000,
                           hold_stances=1,frost_variants=[0,12,17],frost_milliseconds=750,frost_speed=8)
        self.assertEqual(len(encode_session(self.config,self.pid,self.born)),4168)
        bad=copy.deepcopy(self.config);bad['hold_camera_bank']=0
        with self.assertRaisesRegex(ValueError,'camera'):
            encode_session(bad,self.pid,self.born)
        for index,field,value in ((4,'id','jin_hayabusa.third_launcher'),(4,'motion',5013),
                (4,'source_payload_prefix','00'),(4,'replacement',low['replacement']),
                (5,'key',0xC7B),(5,'adapter_kind',2),(5,'recovery_frame',0),
                (5,'ki_cost',1),(5,'transition_count',20),(5,'next_variant',8),(5,'next_end',1)):
            bad=copy.deepcopy(moves);bad[index][field]=value
            with self.subTest(index=index,field=field), self.assertRaises(ValueError):
                check_import_topology(bad,None)
        settings['frost_moon']['mid']=None
        self.assertEqual([move['key'] for move in prepare.configured_replacements(settings)['moves']],
                         [0xC6E,0xC6F,0xC70,0xC79,0xCAC,0xCAD])
        settings=copy.deepcopy(DEFAULT_PRESET);settings['frost_moon']['low']='jin_hayabusa.action_0c71'
        complete=prepare.configured_replacements(settings)
        self.assertEqual((len(complete['moves']),complete['hold_stances']), (15,1))
        flying=[move for move in complete['moves'] if 0xC71<=move['key']<=0xC74]
        self.assertEqual([(move['key'],move['ki_cost']) for move in flying],[(0xC71,0),(0xC72,20),(0xC73,0),(0xC74,0)])
        for source in flying:
            move=copy.deepcopy(source);address=0x500000+move['key']*0x1000
            move.update(descriptor=address,payload=address+0x100,clip=address+0x200,timing_record=address+0x300)
            adapter=dict(action_resource=0x910000,timing_resource=0x920000,bank=0x930000,
                         motion_bank=0x940000,timing_wrapper=0x950000,kind=move['adapter_kind'],
                         player_descriptor=0xA00000+0xCF5*0x100,**move['replacement'])
            self.config['imports'].append(move);self.config['adapters'].append(adapter)
        self.config['frost_variants'][0]=19
        self.assertEqual(len(encode_session(self.config,self.pid,self.born)),4168)
        for index,field,value in ((18,'flags',1),(18,'transition_count',17),(19,'ki_cost',0),(20,'adapter_kind',2),(21,'recovery_frame',-1)):
            bad=copy.deepcopy(self.config);bad['imports'][index][field]=value
            with self.subTest(phase=index,field=field),self.assertRaises(ValueError):
                encode_session(bad,self.pid,self.born)

    def test_native_pair_cannot_become_a_timed_or_direct_combo_link(self):
        # Keep paired success separate from timed links and direct gesture entry.
        # Alter paired-success linkage and entry configuration in the import table.
        # Victim-dependent actions must remain native-success handoffs rather than timed forced dispatches.
        for index,field,value in ((4,'next_variant',6),(5,'next_end',10),(5,'next_variant',2),
                                 (6,'next_variant',2),(6,'recovery_frame',10),(2,'flags',0xFFFFFFFF)):
            config=copy.deepcopy(self.config);config['imports'][index][field]=value
            with self.subTest(index=index,field=field), self.assertRaises(ValueError):
                encode_session(config,self.pid,self.born)

    def test_export_allocation_freed_after_completion_but_retained_after_timeout(self):
        # Release export arguments only after native completion is known.
        # Acknowledge session writes, then simulate completed or pending export threads.
        # Remote arguments stay alive until the native caller has definitely finished reading them.
        args = SimpleNamespace(timeout_ms=100)
        def write(handle, address, payload, size, written):
            # Acknowledge writing the entire session blob to fixture remote memory.
            # Set the ctypes byte-count output to the requested size.
            # Allocation lifetime tests must reach export execution without real process writes.
            C.cast(written, C.POINTER(loader.SIZE)).contents.value = size
            return True
        for timeout in (False, True):
            loader.reset_progress()
            def run(handle, address, parameter, timeout_ms, on_created):
                # Signal that the simulated export thread was created.
                # Raise PendingThread only for the timeout scenario, otherwise return completion.
                # A pending thread still owns the argument blob and forbids immediate release.
                on_created()
                if timeout:
                    raise loader.PendingThread('owned timeout')
                return 0
            with patch.object(loader.K, 'VirtualAllocEx', return_value=0x12340000), \
                 patch.object(loader.K, 'WriteProcessMemory', side_effect=write), \
                 patch.object(loader.K, 'VirtualFreeEx', return_value=True) as free, \
                 patch.object(loader, 'validate_target'), patch.object(loader, 'run_thread', side_effect=run):
                if timeout:
                    with self.assertRaisesRegex(loader.PendingThread, 'retained session-config'):
                        loader.call_export(1, args, 2, b'config')
                    free.assert_not_called()
                else:
                    self.assertEqual(loader.call_export(1, args, 2, b'config'), 0)
                    free.assert_called_once_with(1, 0x12340000, 0, 0x8000)
