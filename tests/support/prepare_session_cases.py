import contextlib
import copy
import io
import json
from pathlib import Path
import re
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
MOD_ROOT = ROOT.parent/'SKM'
sys.path.insert(0, str(ROOT / 'runtime'))
import prepare_session as prepare

from session_fixture import PROFILE, BOSS, FIXTURES


class ImportMemory:
    def __init__(self):
        # Build owned source descriptors, transitions and timing rows for every manifest import.
        # Encode pointers and source fields in their actual native layouts.
        # Preparation must validate current source bytes rather than reuse cached move assumptions.
        self.memory = {}
        self.manifest = prepare.read_import_manifest(MOD_ROOT/'data/imports/okatsu.json')
        self.bank, self.table = 0x110000, 0x120000
        self.put(self.bank, bytes(0x138))
        self.put(self.bank+0x128, struct.pack('<QI',self.table,len(BOSS['imports'])))
        self.motion, self.timing, self.rows = {}, {}, {}
        for index, move in enumerate(BOSS['imports']):
            descriptor, payload, record = (move[field] for field in ('descriptor','payload','timing_record'))
            self.put(self.table+index*8,struct.pack('<Q',descriptor))
            desc, body = bytearray(0xD0), bytearray(0xB0)
            struct.pack_into('<I',desc,0,move['key']);desc[0x40]=1
            struct.pack_into('<Q',desc,0x20,payload)
            pointer_table = 0x70000000+index*0x10000
            struct.pack_into('<QHH',desc,0x78,pointer_table,0,move['transition_count'])
            struct.pack_into('<h',body,0x16,move['ki_cost'])
            struct.pack_into('<Qih',body,0x18,move['flags'],move['motion'],move['recovery_frame'])
            struct.pack_into('<i',body,0x34,-1)
            self.put(descriptor,desc);self.put(payload,body)
            for position in range(move['transition_count']):
                address = pointer_table+0x1000+position*0x30
                self.put(pointer_table+position*8,struct.pack('<Q',address))
                row = bytearray(0x30)
                if position == 0 and move['next_variant'] != -1:
                    struct.pack_into('<h',row,0x14,BOSS['imports'][move['next_variant']]['key'])
                    struct.pack_into('<hh',row,0x20,move['next_start'],move['next_end'])
                    if move['flags'] == prepare.GRAB_ATTEMPT_FLAGS:
                        struct.pack_into('<H',row,0,22)
                        row[11]=0xff
                self.put(address,row)
            self.rows[index] = pointer_table+0x1000
            timing = bytearray(0x100+(max(voice['index'] for voice in move['voices'])+1)*0x4c)
            struct.pack_into('<II',timing,4,len(move['voices']),0x24)
            struct.pack_into('<I',timing,0x10,0x100)
            for voice_index,voice in enumerate(move['voices']):
                struct.pack_into('<III',timing,0x24+voice_index*12,voice['frame'],10,voice['index'])
                struct.pack_into('<I',timing,0x100+voice['index']*0x4c+0x1c,voice['hash'])
                struct.pack_into('<I',timing,0x100+voice['index']*0x4c+0x40,12)
            self.put(record,timing)
            self.motion[move['motion']] = dict(presence='present',clip=hex(move['clip']))
            self.timing[move['motion']] = dict(presence='present',record=hex(record))

    def put(self,address,data):
        # Install bytes at explicit fixture addresses.
        # Replace overlapping bytes directly in the sparse memory dictionary.
        # Individual source-field corruption must be isolated without rebuilding all fixtures.
        self.memory.update({address+index:value for index,value in enumerate(data)})

    def bytes(self,address,size):
        # Read an exact source range from populated fixture memory.
        # Require every requested byte to exist.
        # Unknown addresses must fail instead of silently supplying plausible zero data.
        return bytes(self.memory[address+index] for index in range(size))

    def begin_sample(self):
        # Expose the production stable-read sampling boundary.
        # Perform no invalidation because fixture memory has no OS region cache.
        # Preparation can use its regular reader contract entirely offline.
        pass

    def resolve(self):
        # Run import resolution against the real manifest and owned bank bytes.
        # Patch only motion/timing resource lookup to the corresponding fixture records.
        # Stable-read pins and source-family validation remain production behavior under test.
        stable = prepare.StableReads(self)
        with patch.object(prepare,'inspect_motion',side_effect=lambda game,pins,bank,key:(
            # Resolve an imported motion key from its owned fixture resource table.
            # Index the exact requested key and let missing entries fail.
            # Preparation must not silently replace a missing clip with a different animation.
            self.motion[key]
        )), \
             patch.object(prepare,'inspect_timing',side_effect=lambda game,pins,wrapper,key:(
                 # Resolve an imported timing key from the owned timing fixture table.
                 # Return its exact record and configured row data.
                 # Source voice and timing validation must inspect the intended action's events.
                 self.timing[key]
             )):
            resolved, imports = prepare.resolve_imports(self,stable,self.bank,0x510000,0x520000,self.manifest)
        return stable, resolved, imports


class PreparationTests(unittest.TestCase):
    def setUp(self):
        # Keep baseline preparation cases independent of the selected player trial.
        # Disable only the replacement manifest loader while retaining production resource checks.
        # Dedicated replacement tests explicitly supply their own candidate fixtures.
        configured = patch.object(prepare, 'configured_replacements', return_value=None)
        configured.start()
        self.addCleanup(configured.stop)

    def test_player_replacement_pins_high_transition_slice_and_rejects_changed_rows(self):
        # Resolve William's recorded CF5 descriptor with transition indices above 4096.
        # Pin all 46 player rows, then mutate a row and the recorded payload family independently.
        # Preparation must retain native directional transitions and reject changes before publication.
        game=ImportMemory()
        descriptor,payload,table=0xA10000,0xA20000,0xA30000
        desc,body=bytearray(0xD0),bytearray(0xB0)
        struct.pack_into('<I',desc,0,0xCF5);desc[0x40]=1
        struct.pack_into('<Q',desc,0x20,payload)
        struct.pack_into('<QHH',desc,0x78,table,6759,46)
        struct.pack_into('<Qih',body,0x18,0x8000000594C0000,4300,38)
        game.put(descriptor,desc);game.put(payload,body)
        for index in range(46):
            game.put(table+(6759+index)*8,struct.pack('<Q',0xB10000+index*0x30))
            game.put(0xB10000+index*0x30,bytes(0x30))
        move=dict(adapter_kind=1,replacement=dict(player_key=0xCF5,player_motion=4300,transition_count=46,recovery_frame=38))
        group=dict(action_resource=0xC10000,timing_resource=0xC20000,bank=0xC30000,
                   motion_bank=0xC40000,timing_wrapper=0xC50000)
        entry=dict(descriptor=hex(descriptor),payload=hex(payload))
        stable=prepare.StableReads(game)
        with patch.object(prepare,'inspect_banks'),patch.object(prepare,'resolve',return_value=entry):
            adapter=prepare.player_replacement(game,stable,PROFILE['player'],move,group)
            self.assertEqual(adapter,dict(group,player_descriptor=descriptor,kind=1,**move['replacement']))
            stable.check()
            game.put(0xB10000,bytes([1]))
            with self.assertRaisesRegex(ValueError,'Resource identity changed'):stable.check()
            game.put(payload+0x18,struct.pack('<Q',0x194C0000))
            with self.assertRaisesRegex(ValueError,'source signature'):
                prepare.player_replacement(game,prepare.StableReads(game),PROFILE['player'],move,group)
        with patch.object(prepare,'inspect_banks'),patch.object(prepare,'resolve',return_value=None):
            with self.assertRaisesRegex(ValueError,'descriptor is absent'):
                prepare.player_replacement(game,prepare.StableReads(game),PROFILE['player'],move,group)

    def test_preparation_detects_other_workspace_active_runtime_without_saved_cache(self):
        # Detect a running runtime from another workspace without trusting a saved cache.
        # Expose an active tagged trace while removing the local cached session.
        # Preparation must detect runtime ownership across workspaces before loading another engine.
        tag = '0123456789abcdef'
        closed = []
        class ExistingTrace:
            def __init__(self, pid, prefix, config=None):
                # Expose only the already-active runtime's exact configuration tag.
                # Raise the native not-found error for other mapping names.
                # Preparation must discover an existing workspace runtime without relying on saved cache.
                if config != tag:
                    error = OSError('No mapping'); error.winerror = 2
                    raise error
            def header(self):
                # Report that the fixture runtime is enabled and active.
                # Return only the control fields needed by active-runtime detection.
                # A discovered mapping must prevent unsafe concurrent preparation.
                return dict(enabled=1, status=1)
            def close(self):
                # Record disposal of the detected trace mapping.
                # Use a list marker because no real mapping handle exists.
                # Detection must close its read-only probe before refusing preparation.
                closed.append(True)
        with tempfile.TemporaryDirectory() as folder, patch.object(prepare, 'HERE', Path(folder)), \
             patch.object(prepare, 'modules', return_value=[dict(name=f'boss_repeat_{tag}.dll',
                         path=f'C:/older-workspace/boss_repeat_{tag}.dll')]), \
             patch.object(prepare, 'Trace', ExistingTrace):
            with self.assertRaisesRegex(ValueError, 'active or not cleanly stopped'):
                prepare.require_stopped(1234)
        self.assertEqual(closed, [True])

    def test_preparation_rejects_untagged_runtime_and_uses_pinned_build_hash(self):
        # Reject untagged runtime modules and preserve the pinned compiled-build identity.
        # Present an untagged active runtime and inspect preparation's supported-build check.
        # Unknown runtime ownership cannot be adopted just because process attachment succeeds.
        with patch.object(prepare, 'modules', return_value=[dict(name='nioh_skill_runtime.dll', path='runtime.dll')]):
            with self.assertRaisesRegex(ValueError, 'no discoverable session tag'):
                prepare.require_stopped(1234)
        with tempfile.TemporaryDirectory() as folder:
            binary = Path(folder) / 'snapshot.dll'; binary.write_bytes(b'completed build')
            with patch.dict(prepare.os.environ, {'NIOH_RUNTIME_BUILD_DLL': str(binary)}):
                self.assertEqual(prepare.native_code_hash(), prepare.hashlib.sha256(b'completed build').hexdigest())






    def test_owned_resource_fields_match_runtime_abi_without_source_actor(self):
        # Encode owned resource fields without requiring a source boss actor.
        # Prepare a session using only the player and engine-owned resource fields.
        # The encoded ABI must not require any borrowed source boss object.
        from engine_policy import LAUNCH_PROFILES, TRACKING_RATES
        bindings=dict(hold_stances=0,frost_variants=[0,0,0],frost_milliseconds=0,frost_speed=8,mid_light_ender=False,skill_bindings=[],move_settings=None,controller_selection=0,launch_profiles=copy.deepcopy(LAUNCH_PROFILES),air_juggle_boost=2,tracking_rates=copy.deepcopy(TRACKING_RATES))
        fields, originals = prepare.boss_fields(dict(PROFILE,**bindings))
        expected=dict(BOSS,**bindings)
        self.assertEqual(fields, {key:expected[key] for key in fields})
        self.assertEqual(originals, BOSS['originals'])
        self.assertNotIn('source_actor', fields)
        self.assertNotIn('source_owner', fields)
        bad=copy.deepcopy(PROFILE)
        bad['source']['action_resource']='0x0'
        with self.assertRaisesRegex(ValueError, 'resource absent'):
            prepare.boss_fields(bad)

    def test_current_resource_owner_supplies_the_player_candidate(self):
        # Resolve the current actor exclusively from the owned resource loader.
        # Supply fresh identities and reject a changed native player candidate.
        # A previous session's cache must not replace runtime address discovery.
        game=type('Game', (), {'identity':PROFILE['session'], 'begin_sample':lambda self:(
            # Accept the stable-read sample boundary in this minimal player fixture.
            # Perform no cache reset because resource inspection is separately mocked.
            # The stale-cache test must reach current resource resolution without game access.
            None
        )})()
        handles=(BOSS['source_action_resource'], BOSS['source_timing_resource'], BOSS['source_motion_bank'],
                 BOSS['source_camera_bank'],BOSS['player']+0x1000,BOSS['player_owner']+0x1000)
        with patch.object(prepare, 'load_resources', return_value=handles) as resources, \
             patch.object(prepare, 'StableReads'), \
             patch.object(prepare, 'inspect_candidate', return_value={'role':'replaced_actor'}) as inspect, \
             patch('boss_probe.discover') as discover:
            with self.assertRaisesRegex(ValueError, 'player candidate changed'):
                prepare.fresh_profile(game)
        resources.assert_called_once_with(game)
        self.assertEqual(inspect.call_args.args[2], {'object':hex(handles[4]),'owner_like':hex(handles[5])})
        discover.assert_not_called()

    def test_native_resource_failure_cannot_fall_back_to_saved_boss_pointers(self):
        # Expose resource-loading failure instead of falling back to saved boss pointers.
        # Fail native owned-resource loading in the presence of old profile data.
        # Preparation must surface the missing resource instead of reviving unsafe borrowed pointers.
        game=object()
        with patch.object(prepare,'load_resources',side_effect=ValueError('resource generation changed')), \
             patch.object(prepare,'inspect_candidate') as inspect:
            with self.assertRaisesRegex(ValueError,'resource generation changed'):
                prepare.fresh_profile(game)
        inspect.assert_not_called()

    def test_import_lookup_pins_native_actions_transitions_and_voice_rows(self):
        # Pin imported actions, transitions and voice rows against concurrent changes.
        # Resolve all manifest imports against owned native descriptors and timing records.
        # Every accepted source field must be included in stable-read validation before publication.
        game=ImportMemory()
        stable,resolved,imports=game.resolve()
        self.assertEqual(imports,BOSS['imports'])
        self.assertEqual([entry['motion'] for entry in resolved],[1220,1230,1210,1211,1212,1310,1311])
        stable.check()
        game.put(BOSS['imports'][2]['payload']+0x24,struct.pack('<h',53))
        with self.assertRaisesRegex(ValueError,'Resource identity changed'):
            stable.check()

    def test_paired_family_and_unverified_import_metadata_are_rejected(self):
        # Reject unsupported paired families and unresolved import metadata.
        # Corrupt source families, recovery, row counts and configured vocal rows individually.
        # Only researched capability families with exact source evidence may enter the runtime table.
        imported=BOSS['imports'][2]
        voice=imported['voices'][0]
        changes=[(imported['payload']+0x18,'<Q',0x594C0000,'action family'),
                 (imported['payload']+0x18,'<Q',0x8078000000,'action family'),
                 (imported['payload']+0x24,'<h',53,'recovery frame'),
                 (imported['descriptor']+0x82,'<H',13,'transition count'),
                 (imported['timing_record']+0x24,'<I',23,'voice event'),
                 (imported['timing_record']+0x100+voice['index']*0x4c+0x1c,'<I',1,'voice hash/category'),
                 (imported['timing_record']+0x100+voice['index']*0x4c+0x40,'<I',11,'voice hash/category')]
        for address,format,value,message in changes:
            with self.subTest(message=message,value=value):
                game=ImportMemory();game.put(address,struct.pack(format,value))
                with self.assertRaisesRegex(ValueError,message):game.resolve()
        game=ImportMemory();game.put(game.rows[2]+0x20,struct.pack('<h',29))
        with self.assertRaisesRegex(ValueError,'combo window'):game.resolve()
        game=ImportMemory();game.motion[1210]={'presence':'absent'}
        with self.assertRaisesRegex(ValueError,'did not resolve'):game.resolve()
        game=ImportMemory();game.put(game.rows[5],struct.pack('<H',0))
        with self.assertRaisesRegex(ValueError,'paired success'):game.resolve()

    def test_camera_resource_and_imported_slot_are_pinned_before_session_publication(self):
        # Pin camera resource and imported slot0 independently of idle camera selection.
        # Prepare idle camera indices one and two while importing through slot zero.
        # The recorded slot and active index must remain stable, including a valid null slot-zero original.
        first=dict(resolution=PROFILE['source']['action_resolution'],motion=1220,
                   motion_resource={key:value for key,value in PROFILE['source']['resources']['motion']['banks'][0].items() if key!='slot'},
                   timing_resource={key:value for key,value in PROFILE['source']['resources']['timing']['banks'][0].items() if key!='slot'})
        handles=tuple(BOSS[key] for key in ('source_action_resource','source_timing_resource',
                                           'source_motion_bank','source_camera_bank','player','player_owner'))
        camera=BOSS['player_camera_slot']-8
        resources=(copy.deepcopy(PROFILE['player']['resources']),
                   [BOSS['originals'][0],0,0,0,BOSS['originals'][1]],
                   [BOSS['originals'][2],0,0,BOSS['originals'][3]])
        for index, changed in ((0,False),(1,False),(2,False),(3,False),(-1,False),(0,True)):
            with self.subTest(index=index,changed=changed):
                game=ImportMemory();game.identity=PROFILE['session']
                game.put(BOSS['source_action_resource']+0x468,struct.pack('<Q',game.bank))
                game.put(BOSS['source_timing_resource']+0x468,struct.pack('<Q',0x710000))
                game.put(BOSS['source_camera_bank'],struct.pack('<Q',int(game.identity['module_base'],0)+0x13C8FA0))
                game.put(BOSS['player_owner']+0x48,struct.pack('<Q',camera))
                game.put(camera+0x20,struct.pack('<i',index))
                for slot in range(3):game.put(camera+8+slot*8,struct.pack('<Q',BOSS['camera_original']+slot*0x100 if slot else 0))
                def inspect_resources(*args):
                    # Return source resource metadata during camera preparation.
                    # Optionally switch the player's active camera index during that inspection.
                    # Stable preparation must reject a changing component instead of publishing torn camera state.
                    if changed:game.put(camera+0x20,struct.pack('<i',1))
                    return copy.deepcopy(resources)
                with patch.object(prepare,'load_resources',return_value=handles), \
                     patch.object(prepare,'inspect_candidate',return_value=copy.deepcopy(PROFILE['player'])), \
                     patch.object(prepare,'resolve_imports',return_value=([first,PROFILE['charged_candidate']],BOSS['imports'])), \
                     patch.object(prepare,'inspect_motion',return_value={'presence':'present','clip':'0x56000000'}), \
                     patch.object(prepare,'resources',side_effect=inspect_resources), \
                     patch.object(prepare,'compiled_skill_bindings',return_value=[]):
                    if index not in (0,1,2) or changed:
                        with self.assertRaises(ValueError):prepare.fresh_profile(game)
                    else:
                        profile=prepare.fresh_profile(game)
                        fields,_=prepare.boss_fields(profile)
                        self.assertEqual(fields['player_camera_slot'],camera+8)
                        self.assertEqual(fields['camera_original'],0)
                        self.assertEqual(fields['source_camera_bank'],BOSS['source_camera_bank'])
