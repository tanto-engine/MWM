# Offline regression cases for the shared Python/native binary session layout and its bounds.
# Fixtures isolate game/process effects; these checks do not establish gameplay acceptance.
# Loaded by the existing Engine test entrypoints through Test-Offline.ps1; see CODE_GUIDE.md.
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
MOD_ROOT = ROOT/'mwm'
ORIGINAL_PRESET = json.loads((MOD_ROOT/'data/presets/sword-original.json').read_text())
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

    def test_ordinary_frost_import_can_serve_another_stance_binding(self):
        self.config['frost_variants']=[0,1,0]
        self.config['skill_bindings']=[dict(kind=1,stances=4,variant=1,key=0xCB7,
            motion=3300,transition_count=40,flags=0x8000000594C0000)]
        self.assertEqual(len(encode_session(self.config,self.pid,self.born)),SESSION_CONFIG.size)

    def test_pointer_order_matches_native_abi(self):
        # Keep Python session packing identical to the native ABI field order.
        # Encode a complete session and unpack its fixed header and pointer sequence.
        # Version seven places the stance mask, Frost slots, window and startup speed before resource pointers.
        values = SESSION_CONFIG.unpack(encode_session(self.config, self.pid, self.born))
        self.assertEqual(values[:16], (MAGIC, VERSION, SESSION_CONFIG.size, self.pid, self.born,
                                      0x123456789abcdef0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 8))
        self.assertEqual(values[16:42], tuple(self.config[key] for key in POINTER_FIELDS)
                         + tuple(self.config['originals']))
        self.assertEqual(values[42:44], (7,2))
        encoded = encode_session(self.config, self.pid, self.born)
        move = MOVE_IMPORT.unpack_from(encoded,328+2*96)
        self.assertEqual(move[4:13], (0x184C0000,0xC61,1210,52,14,3,30,45,1))
        self.assertEqual(move[13:16], (22,12,0x297D2215))
        self.assertEqual(encoded[328+7*96:6472], bytes(57*96))
        self.assertEqual(encoded[6472:11592], bytes(64*64+32*32))
        grapple = dict(self.config, native_grapple=True)
        enabled = encode_session(grapple, self.pid, self.born)
        self.assertEqual(SESSION_CONFIG.unpack(enabled)[9], 1)
        self.assertEqual(enabled[64:], encoded[64:])
        for value in (1, None, 'true'):
            with self.subTest(grapple=value), self.assertRaisesRegex(ValueError, 'must be a boolean'):
                encode_session(dict(self.config, native_grapple=value), self.pid, self.born)
        header = (ROOT / 'runtime/native/boss_session_schema.h').read_text()
        import re
        self.assertEqual(re.findall(r'^    uint64_t (\w+);$', header.split('struct MoveVoice')[0], re.MULTILINE), list(POINTER_FIELDS))

    def test_chord_reservations_are_encoded_and_bounded(self):
        self.config['chord_reservations']=[dict(buttons=0x8100,stances=1,mode=0),
                                           dict(buttons=0x2100,stances=7,mode=0)]
        encoded=encode_session(self.config,self.pid,self.born)
        self.assertEqual(encoded[12416:12424],bytes.fromhex('0081010000210700'))
        self.assertEqual(encoded[12424:12544],bytes(120))
        self.assertEqual(encoded[12544:12552],bytes.fromhex('0200000000000000'))
        for rows in ([dict(buttons=0x8100,stances=1,mode=0)]*2,
                     [dict(buttons=0x8100,stances=0,mode=0)],
                     [dict(buttons=0xC00,stances=7,mode=1)],
                     [dict(buttons=0x200,stances=1,mode=0)],
                     [dict(buttons=0x8100,stances=1,mode=2)]):
            with self.subTest(rows=rows),self.assertRaisesRegex(ValueError,'chord reservation'):
                encode_session(dict(self.config,chord_reservations=rows),self.pid,self.born)

    def test_sequence_reservation_encodes_ordered_followup(self):
        self.config['chord_reservations']=[dict(buttons=0x2100,stances=1,mode=10)]
        self.assertEqual(encode_session(self.config,self.pid,self.born)[12416:12420],
                         bytes.fromhex('0021010a'))
        for buttons,mode in ((0x8100,10),(0x2100,1),(0x2100,12)):
            with self.subTest(buttons=buttons,mode=mode),self.assertRaisesRegex(ValueError,'chord reservation'):
                encode_session(dict(self.config,chord_reservations=[dict(buttons=buttons,stances=1,mode=mode)]),
                               self.pid,self.born)

    def test_plain_chord_reservations_retain_global_buttons_without_widening_sequences(self):
        from prepare_session import compiled_chord_reservations
        from game_controller import GAME_DEVICE
        from engine_config import DEFAULT_PRESET
        calibration = dict(device=GAME_DEVICE, lb_mask=0x100)
        preset = dict(DEFAULT_PRESET, tap_move='okatsu.charged_rush', hold_move=None,
                      modifier_mask=0x100, skill_bindings=[])
        for trigger in (0x800, 0x1000, 1):  # R2, Cross and D-pad up were offered by the global chord editor.
            with self.subTest(trigger=trigger):
                preset['trigger_mask'] = trigger
                reservations = compiled_chord_reservations(preset, calibration, self.config['imports'])
                self.assertEqual(reservations, [dict(buttons=0x100|trigger, stances=1, mode=0)])
                encoded = encode_session(dict(self.config, chord_reservations=reservations), self.pid, self.born)
                self.assertEqual(encoded[12416:12420], (0x100|trigger).to_bytes(2,'little')+bytes((1,0)))
                with self.assertRaisesRegex(ValueError, 'chord reservation'):
                    encode_session(dict(self.config, chord_reservations=[dict(reservations[0], mode=4)]), self.pid, self.born)
        preset['trigger_mask'] = 0x200
        with self.assertRaisesRegex(ValueError, 'R1 / RB is reserved'):
            compiled_chord_reservations(preset, calibration, self.config['imports'])
        with self.assertRaisesRegex(ValueError, 'chord reservation'):
            encode_session(dict(self.config, chord_reservations=[dict(buttons=0x300, stances=1, mode=0)]), self.pid, self.born)

    def test_full_import_capacity_and_overflow(self):
        # The former 32-phase cap rejected otherwise valid authored movesets.
        # Encode every available slot, then reject an additional phase before packing.
        # Native coverage separately verifies cycle detection beyond index 31.
        from move_imports import IMPORT_LIMIT
        for index in range(len(self.config['imports']),IMPORT_LIMIT):
            move=copy.deepcopy(self.config['imports'][0])
            move.update(id=f'fixture.action_{index}',key=0x100+index,next_variant=-1,next_start=0,next_end=0)
            self.config['imports'].append(move);self.config['adapters'].append(None)
        encoded=encode_session(self.config,self.pid,self.born)
        self.assertEqual(SESSION_CONFIG.unpack(encoded)[42],IMPORT_LIMIT)
        from gestures import ControllerGesture
        calibration=dict(device={},lb_mask=1)
        binding=dict(device={},lb_mask=1,circle_mask=2,hold_seconds=.25,variants=[32,IMPORT_LIMIT-1])
        self.assertEqual(ControllerGesture(calibration,binding,1000).variants,[32,IMPORT_LIMIT-1])
        self.config['imports'].append(copy.deepcopy(move));self.config['adapters'].append(None)
        with self.assertRaisesRegex(ValueError,f'1 to {IMPORT_LIMIT}'):
            encode_session(self.config,self.pid,self.born)

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
        manifest = read_import_manifest(MOD_ROOT/'data/imports/jin_hayabusa.json')
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
        self.assertEqual(encoded[6472:6472+7*64], bytes(7*64))
        self.assertEqual(MOVE_ADAPTER.unpack_from(encoded,6472+7*64),
            (0x910000,0x920000,0x930000,0x940000,0x950000,0xA10000,0xCF5,4300,46,38,1))
        self.assertEqual(encoded[6472+10*64:11592], bytes(54*64+32*32))
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
        manifest = read_import_manifest(MOD_ROOT/'data/imports/okatsu.json')
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
        raw=json.loads((MOD_ROOT/'data/imports/okatsu.json').read_text())
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

    def configured_fixture(self, settings):
        # Compile real preset dependencies against owned deterministic resource addresses.
        # Preserve baseline signatures and source alias identity while relocating adapter pointers.
        # Exercise the same table encoder used by live preparation without touching Nioh.
        import prepare_session as prepare
        baseline=prepare.configured_imports(settings)
        compiled=prepare.configured_replacements(settings,baseline)
        originals={move['id']:move for move in self.config['imports']}
        self.config['imports']=[copy.deepcopy(originals[move['id']]) for move in baseline['moves']]
        offset=len(self.config['imports']);self.config['adapters']=[None]*offset
        self.config['string_variant']=baseline['string_variant']
        for source in compiled['moves'] if compiled else []:
            move=copy.deepcopy(source);address=0x500000+move['key']*0x1000
            move.update(descriptor=address,payload=address+0x100,clip=address+0x200,timing_record=address+0x300)
            if move['next_variant']>=0: move['next_variant']+=offset
            template=move.get('replacement',dict(player_key=0,player_motion=0,transition_count=0,recovery_frame=0))
            adapter=dict(action_resource=0x910000,timing_resource=0x920000,bank=0x930000,
                motion_bank=0x940000,timing_wrapper=0x950000,kind=move['adapter_kind'],
                player_descriptor=0xA00000+template['player_key']*0x100 if template['player_key'] else 0,**template)
            self.config['imports'].append(move);self.config['adapters'].append(adapter)
        entry=compiled['hold_variant'] if compiled else 0
        slots={move['id']:index+1 for index,move in enumerate(self.config['imports'])}
        self.config.update(hold_variant=entry+offset if entry else 0,hold_milliseconds=250 if entry else 0,
            hold_camera_bank=0x960000 if any(a and a['kind']==3 for a in self.config['adapters']) else 0,
            hold_stances=sum(1<<i for i,move in enumerate(settings['stance_holds'].values()) if move),frost_variants=[slots.get(move,0) for move in settings['frost_moon'].values()],
            native_grapple=settings['okatsu_grapple'],mid_light_ender=settings['mid_light_ender'],
            skill_bindings=prepare.compiled_skill_bindings(settings,self.config['imports']),
            move_settings=prepare.compiled_move_settings(settings,self.config['imports']))
        if not self.config['hold_variant'] and self.config['hold_stances']:
            self.config['hold_variant']=next(slots[move] for move in settings['stance_holds'].values() if move)
            self.config['hold_milliseconds']=round(settings['hold_seconds']*1000)
        return compiled

    def test_sword_preset_expands_only_selected_stance_dependencies(self):
        # Rotate a sword move across stance templates independently of its source identity.
        # Verify the revised Mid somersault and High guard Izuna graphs and native-source bindings.
        # Reject incompatible graph ownership rather than letting one binding steal another's stance.
        import prepare_session as prepare
        settings=copy.deepcopy(ORIGINAL_PRESET);compiled=self.configured_fixture(settings)
        self.assertEqual([move['key'] for move in compiled['moves']],
            [0xC6E,0xC6F,0xC70,0xC79,0xC71,0xC72,0xC73,0xC74,0xC81,0xC82,0xC83,0xC75,0xC77,0xC78,0xC79,0xC7A,0x3B2,0x3B4,0x3B6,0xBBF,0xC63,0xC64,0xC65,0xC66])
        self.assertEqual((compiled['hold_stances'],compiled['frost_variants']), (1,[5,9,12]))
        from engine_config import binding_for_preset
        binding=binding_for_preset(dict(device={},lb_mask=1),settings,self.config['imports'])
        self.assertEqual(binding['variants'],[0,None])
        self.assertEqual(self.config['adapters'][22]['kind'],2)
        encoded=encode_session(self.config,self.pid,self.born);values=SESSION_CONFIG.unpack(encoded)
        self.assertEqual((values[9],values[42],len(encoded)),(5,27,SESSION_CONFIG.size))
        self.assertEqual(self.config['skill_bindings'],[
            dict(kind=1,stances=7,variant=1,key=0xFAA,motion=5090,transition_count=21,flags=0x40017C00000),
            dict(kind=2,stances=4,variant=18,key=0,motion=0,transition_count=0,flags=0),
            dict(kind=1,stances=1,variant=5,key=0xBC8,motion=-1,transition_count=18,flags=0),
            dict(kind=1,stances=2,variant=23,key=0xC7A,motion=2300,transition_count=42,flags=0x8000000594C0000),
            dict(kind=1,stances=2,variant=23,key=0xBC8,motion=-1,transition_count=18,flags=0),
            dict(kind=3,stances=1,variant=7,key=0,motion=0,transition_count=0,flags=0)])
        for field,value in (('kind',4),('stances',True),('variant',0),('key',0xFAB),('flags',0),('transition_count',20)):
            bad=copy.deepcopy(self.config);bad['skill_bindings'][0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):encode_session(bad,self.pid,self.born)
        bad=copy.deepcopy(self.config);bad['skill_bindings'].append(bad['skill_bindings'][0])
        with self.assertRaisesRegex(ValueError,'Overlapping'): encode_session(bad,self.pid,self.born)
        settings['skill_bindings']=[dict(source='tiger_sprint',stance='mid',move='okatsu.leaping_slash')]
        bindings=prepare.compiled_skill_bindings(settings,self.config['imports'])
        self.assertEqual((bindings[0]['variant'],bindings[0]['stances']),(2,2))
        settings['hold_move']=None;settings['skill_bindings']=[];settings['frost_moon']=dict(low=None,mid=None,high=None);settings['low_heavy']=None
        settings['stance_holds']=dict(low=None,mid='jin_hayabusa.action_0c79',high=None)
        held=prepare.configured_replacements(settings)
        self.assertEqual([(m['key'],m['replacement']['player_key']) for m in held['moves']],[(0xC79,0xC7A)])
        settings['stance_holds']['mid']=None
        self.assertIsNone(prepare.configured_replacements(settings))
        settings['skill_bindings']=[dict(source='tiger_sprint',stance='any',move='jin_hayabusa.flying_swallow_jump')]
        jump=prepare.configured_replacements(settings)
        self.assertIsNotNone(jump)
        self.assertEqual([(m['key'],m['adapter_kind']) for m in jump['moves']],[(0xC71,5)])

    def test_izuna_alias_preserves_launcher_and_rejects_corrupt_graphs(self):
        # Low standalone C79 and high Izuna share source bytes but own distinct graphs.
        # Corrupt alias identity, native paired links, airborne phase metadata and stance ownership.
        # Neither source duplication nor configuration can force a paired action without contact.
        compiled=self.configured_fixture(copy.deepcopy(ORIGINAL_PRESET))
        moves=compiled['moves'];low,izuna=moves[3],moves[14]
        check_import_topology(moves,None)
        self.assertEqual((low['replacement']['player_key'],izuna['replacement']['player_key']),(0xCF5,0xCB7))
        for index,field,value in ((14,'id','jin_hayabusa.third_launcher'),(14,'motion',5013),
                (14,'source_payload_prefix','00'),(14,'replacement',low['replacement']),
                (15,'key',0xC7B),(15,'adapter_kind',2),(15,'recovery_frame',0),(15,'ki_cost',1),
                (15,'transition_count',20),(15,'next_variant',18),(15,'next_end',1),
                (4,'flags',1),(5,'ki_cost',0),(6,'adapter_kind',2),(7,'recovery_frame',-1),
                (8,'motion',1051),(9,'ki_cost',0),(10,'transition_count',74)):
            bad=copy.deepcopy(moves);bad[index][field]=value
            with self.subTest(index=index,field=field),self.assertRaises(ValueError):check_import_topology(bad,None)
        for field,value in (('hold_camera_bank',0),('frost_variants',[8,15,0]),('frost_variants',[8,12]),
                ('frost_milliseconds',99),('frost_speed',9),('hold_stances',8)):
            bad=copy.deepcopy(self.config);bad[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):encode_session(bad,self.pid,self.born)

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
            with patch.object(loader.K, 'VirtualAllocEx', return_value=0x12647200), \
                 patch.object(loader.K, 'WriteProcessMemory', side_effect=write), \
                 patch.object(loader.K, 'VirtualFreeEx', return_value=True) as free, \
                 patch.object(loader, 'validate_target'), patch.object(loader, 'run_thread', side_effect=run):
                if timeout:
                    with self.assertRaisesRegex(loader.PendingThread, 'retained session-config'):
                        loader.call_export(1, args, 2, b'config')
                    free.assert_not_called()
                else:
                    self.assertEqual(loader.call_export(1, args, 2, b'config'), 0)
                    free.assert_called_once_with(1, 0x12647200, 0, 0x8000)
