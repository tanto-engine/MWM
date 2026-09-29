# Offline regression cases for reviewed move choices, public/private settings and native session encoding.
# Fixtures isolate game/process effects; these checks do not establish gameplay acceptance.
# Loaded by the existing Engine test entrypoints through Test-Offline.ps1; see CODE_GUIDE.md.
import copy
import struct
import unittest
from unittest.mock import patch

import engine_config as config
import prepare_session as prepare
from engine_policy import KI_PULSE
from runtime_session import encode_session, MOVE_SETTINGS
import runtime_session_cases as sessions


def empty_preset():
    # Start capability checks with every optional move replacement disabled.
    # Deep-copy the baseline so one test cannot mutate the default used by another.
    # Individual cases enable only the binding or graph whose behavior they are proving.
    return dict(copy.deepcopy(config.DEFAULT_PRESET),tap_move=None,hold_move=None,low_heavy=None,
        stance_holds=dict(low=None,mid=None,high=None),frost_moon=dict(low=None,mid=None,high=None),
        skill_bindings=[],okatsu_grapple=False,mid_light_ender=False,string_enabled=False,move_settings={})


class CapabilityTests(unittest.TestCase):
    def test_hideyori_string_uses_one_continuation_input(self):
        preset=empty_preset()
        preset['stance_holds']['low']='toyotomi_hideyori.action_0d30'
        preset['skill_bindings']=[dict(source='light_attack',stance='low',move='toyotomi_hideyori.action_0d30')]
        with self.assertRaisesRegex(ValueError,'cannot use two inputs'):
            config.validate_preset(preset)

    def fixture(self,preset):
        # Create a native-shaped session for an edited preset without attaching to Nioh.
        # Reuse the maintained session fixture and serialize it through the production ABI encoder.
        # Returning both objects lets cases compare readable settings with their exact native bytes.
        fixture=sessions.RuntimeSessionTests();fixture.setUp();fixture.configured_fixture(preset)
        return fixture,encode_session(fixture.config,fixture.pid,fixture.born)

    def test_reviewed_graphs_compile_for_every_chord_stance_and_frost_destination(self):
        # Check each reviewed graph in every supported stance and Frost destination.
        # Enable one move at a time and verify its compiled import index reaches the correct binding.
        # This proves configuration wiring, not whether that move feels correct in a live fight.
        for move in config.CHORD_MOVES:
            for stance in ('low','mid','high'):
                with self.subTest(move=move,stance=stance):
                    preset=empty_preset();preset.update(tap_move=move,chord_stance=stance)
                    fixture,_=self.fixture(preset)
                    slot=next(i for i,m in enumerate(fixture.config['imports']) if m['id']==move)
                    binding=config.binding_for_preset(dict(device={},lb_mask=1),preset,fixture.config['imports'])
                    self.assertEqual(binding['variants'],[slot,None])
                    preset['tap_move']=None;preset['frost_moon'][stance]=move
                    fixture,_=self.fixture(preset)
                    self.assertGreater(fixture.config['frost_variants'][('low','mid','high').index(stance)],0)

    def test_okatsu_ordinary_moves_support_held_heavy_in_each_stance(self):
        # Reproduce the missing Charged Rush menu/validation path through the real compiler.
        # Ordinary imports retain their own source and can serve independently held stances.
        # Serialize the complete binding and hold metadata without inventing a graph adapter.
        preset=empty_preset()
        preset['stance_holds']=dict(low='okatsu.charged_rush',mid='okatsu.charged_rush',high='okatsu.leaping_slash')
        fixture,_=self.fixture(preset)
        self.assertEqual(fixture.config['hold_stances'],7)
        self.assertEqual([b['variant'] for b in fixture.config['skill_bindings']],[1,1,2])
        choices={move['id']:move['held'] for move in config.move_capabilities()['moves']}
        self.assertTrue(choices['okatsu.charged_rush'])
        self.assertFalse(choices['jin_hayabusa.flying_swallow_jump'])

    def test_speed_and_developer_pulse_reach_graph_phases_and_abi(self):
        # Check that graph phases inherit their root's speed and developer Ki Pulse policy.
        # Decode the actual session bytes at the move-settings offsets and compare every imported phase.
        # Also check the trailing controller/reserved fields so layout drift cannot pass unnoticed.
        preset=empty_preset();preset['tap_move']='jin_hayabusa.action_0c71'
        preset['move_settings']={preset['tap_move']:dict(speed=.5)}
        fixture,_=self.fixture(preset)
        policy=dict(schema_version=1,moves={preset['tap_move']:dict(ki_pulse=dict(percent=65,fill_frames=18,hold_frames=35))})
        fixture.config['move_settings']=prepare.compiled_move_settings(preset,fixture.config['imports'],policy)
        encoded=encode_session(fixture.config,fixture.pid,fixture.born)
        for i,move in enumerate(fixture.config['imports']):
            expected=(.5,65,18,35,0) if move['id'].startswith('jin_hayabusa.') else (1.,40,25,24,0)
            self.assertEqual(MOVE_SETTINGS.unpack_from(encoded,11640+i*MOVE_SETTINGS.size),expected)
        self.assertEqual(struct.unpack_from('<II',encoded,12408),(0,0))

    def test_public_settings_reject_private_fields_and_frame_cuts(self):
        # Keep public presets limited to supported playback choices.
        # Try private policy fields, clip-boundary cuts, invalid numbers and out-of-range speeds.
        # Also reject malformed developer Pulse policy rather than allowing invalid values into native session data.
        preset=empty_preset();move='okatsu.charged_rush'
        for fields in (dict(ki_pulse=KI_PULSE),dict(speed=1,start_frame=2),dict(speed=1,end_frame=30),
                       dict(speed=float('nan')),dict(speed=float('inf')),dict(speed=True),dict(speed=.24),dict(speed=2.01)):
            with self.subTest(fields=fields),self.assertRaises(ValueError):
                config.validate_preset(dict(preset,move_settings={move:fields}))
        for field in ('frost_window_seconds','frost_startup_speed','ki_pulse','launch_profiles','gravity'):
            with self.subTest(field=field),self.assertRaises(ValueError):
                config.validate_preset(dict(preset,**{field:1}))
        for pulse in (dict(percent=101,fill_frames=25,hold_frames=24),dict(percent=40,fill_frames=0,hold_frames=24),
                      dict(percent=40,fill_frames=25,hold_frames=True),dict(percent=40,start_frame=2)):
            with self.assertRaises(ValueError):
                prepare.compiled_move_settings(preset,[],dict(schema_version=1,moves={move:dict(ki_pulse=pulse)}))

    def test_native_heavy_sources_follow_stance_and_controller_slot_is_bounded(self):
        # Check that an all-stance heavy replacement resolves to the three native stance sources.
        # Encode all supported controller selections and inspect the stored selection field.
        # Reject negative, oversized and boolean slots before they can select unintended hardware.
        preset=empty_preset();preset['skill_bindings']=[dict(source='heavy_attack',stance='any',move='okatsu.charged_rush')]
        fixture,encoded=self.fixture(preset)
        self.assertEqual([(b['key'],b['stances']) for b in fixture.config['skill_bindings']],[(0xCF5,1),(0xC7A,2),(0xCB7,4)])
        for selection in range(5):
            fixture.config['controller_selection']=selection
            encoded=encode_session(fixture.config,fixture.pid,fixture.born)
            self.assertEqual(struct.unpack_from('<I',encoded,12408)[0],selection)
        for selection in (5,-1,True):
            with self.assertRaises(ValueError):
                encode_session(dict(fixture.config,controller_selection=selection),fixture.pid,fixture.born)

    def test_quick_attack_source_reaches_each_stance_and_any(self):
        # One native Square source must retain the chosen stance. Graphs require
        # a concrete stance so their William continuation template agrees.
        source=next(s for s in config.move_capabilities()['native_sources'] if s['id']=='light_attack')
        self.assertEqual(source['stances'],['low','mid','high','any'])
        for stance,mask in (('low',1),('mid',2),('high',4),('any',7)):
            with self.subTest(stance=stance):
                preset=empty_preset();preset['skill_bindings']=[dict(source='light_attack',stance=stance,move='okatsu.charged_rush')]
                fixture,_=self.fixture(preset)
                binding=fixture.config['skill_bindings'][0]
                self.assertEqual((binding['kind'],binding['stances'],binding['variant']),(5,mask,1))
        for stance in ('low','mid','high'):
            with self.subTest(graph_stance=stance):
                preset=empty_preset();preset['skill_bindings']=[dict(source='light_attack',stance=stance,move='jin_hayabusa.action_0bbf')]
                fixture,_=self.fixture(preset)
                root=next(m for m in fixture.config['imports'] if m['id']=='jin_hayabusa.action_0bbf')
                self.assertEqual(root['replacement']['player_key'],{'low':0xCF5,'mid':0xC7A,'high':0xCB7}[stance])

    def test_capabilities_exclude_unreviewed_recordings_and_migration_keeps_bindings(self):
        # Keep unimplemented catalogue entries out of the trainer's playable choices.
        # Check supported role flags and migrate an older preset with obsolete public Frost tuning.
        # Migration must reproduce the baseline without modifying the caller's original dictionary.
        caps=config.move_capabilities();moves={m['id']:m for m in caps['moves']}
        self.assertEqual(caps['native_binding_limit'],config.BINDING_LIMIT)
        self.assertEqual({m['id'] for m in caps['moves'] if m['chord']},set(config.CHORD_MOVES))
        self.assertFalse(moves['jin_hayabusa.action_03b2']['speed'])
        self.assertTrue(moves['jin_hayabusa.action_0c6f']['native'])
        self.assertNotIn('jin_hayabusa.action_0cac',moves)
        old=dict(config.DEFAULT_PRESET,schema_version=7,frost_startup_speed=2,frost_window_seconds=.75)
        old.pop('move_settings');old.pop('chord_stance')
        self.assertEqual(config.validate_preset(old),dict(config.DEFAULT_PRESET,move_settings={}))
        self.assertEqual(old['frost_startup_speed'],2)

    def test_frost_shared_import_retains_one_stance_owner(self):
        # Reject two bindings that would give the same imported graph contradictory stance ownership.
        # Check both public preset validation and the lower-level session encoder.
        # A matching single stance is allowed; widening its encoded mask afterward must still be rejected.
        preset=empty_preset();move='jin_hayabusa.action_0c79'
        preset['frost_moon']['high']=move
        preset['skill_bindings']=[dict(source='tiger_sprint',stance='low',move=move)]
        with self.assertRaisesRegex(ValueError,'same stance'): config.validate_preset(preset)
        preset['skill_bindings'][0]['stance']='high'
        fixture,_=self.fixture(preset)
        fixture.config['skill_bindings'][0]['stances']=7
        with self.assertRaisesRegex(ValueError,'graph stance differ'):
            encode_session(fixture.config,fixture.pid,fixture.born)

    def test_graph_chords_and_izuna_roles_require_distinct_concrete_stances(self):
        # Reject settings whose native stance template cannot honor the advertised binding.
        # Launcher and drop share source bytes and need separate stance ownership.
        # Valid rebinding still reaches the native session encoder in every concrete stance.
        for stance in ('low','mid','high'):
            preset=empty_preset();preset.update(tap_move='jin_hayabusa.action_0c79',chord_stance=stance)
            preset['stance_holds'][stance]='jin_hayabusa.izuna_drop'
            with self.assertRaisesRegex(ValueError,'different stances'):config.validate_preset(preset)
            preset['stance_holds'][stance]=None
            preset['stance_holds'][{'low':'mid','mid':'high','high':'low'}[stance]]='jin_hayabusa.izuna_drop'
            self.fixture(preset)
            preset['chord_stance']='any'
            with self.assertRaisesRegex(ValueError,'Choose Low, Mid or High'):config.validate_preset(preset)

    def test_recording_metadata_cannot_promote_native_sources_or_moves(self):
        # Prove that adding a promising-looking recording does not make it executable.
        # Inject catalogue metadata and compare the capabilities/source menu with the reviewed baseline.
        # Unknown source or move IDs must still fail preset validation.
        from catalogue import load_catalogue
        catalogue=load_catalogue();before=config.move_capabilities()
        catalogue['moves'].append(dict(id='unreviewed.captured_action',name='New recording',
            implementation=dict(selectable=True)))
        with patch('catalogue.load_catalogue',return_value=catalogue):
            self.assertEqual(config.move_capabilities(),before)
        self.assertEqual({source['id'] for source in before['native_sources']},
            {'tiger_sprint','dodge_attack','heavy_attack','guard_light','light_attack','high_heavy_followup'})
        for source,move in (('captured_native_skill','okatsu.charged_rush'),('tiger_sprint','unreviewed.captured_action')):
            preset=empty_preset();preset['skill_bindings']=[dict(source=source,stance='mid',move=move)]
            with self.assertRaisesRegex(ValueError,'Unsupported skill binding'):
                config.validate_preset(preset)

    def test_binding_conflicts_explain_controls_stances_and_a_fix(self):
        # Exercise the actual selectable controls rather than malformed internal runtime objects.
        # Every conflict must name the affected choices and leave the submitted draft intact.
        # Different controls may still share a move when they agree on its stance.
        launcher='jin_hayabusa.action_0c79';sanada='sanada_yukimura.action_0c6a';cases=[]
        preset=empty_preset();preset['stance_holds'].update(low=launcher,high=launcher)
        cases.append((preset,(config.move_label(launcher),'Low hold Triangle / Y','High hold Triangle / Y','clear Low')))
        preset=empty_preset();preset['frost_moon'].update(low=launcher,mid=launcher)
        cases.append((preset,('Low Frost Moon','Mid Frost Moon','different move','clear Low')))
        preset=empty_preset();preset['stance_holds']['low']=launcher
        preset['skill_bindings']=[dict(source='heavy_attack',stance='high',move=launcher)]
        cases.append((preset,('Low hold Triangle / Y','High Heavy attack','same stance','clear Low')))
        preset=empty_preset();preset['skill_bindings']=[dict(source='tiger_sprint',stance='any',move=sanada)]
        cases.append((preset,('Tiger Sprint',config.move_label(sanada),'Choose Low, Mid or High','instead of Any')))
        preset=empty_preset();preset.update(tap_move=sanada,chord_stance='any')
        cases.append((preset,('custom chord',config.move_label(sanada),'Choose Low, Mid or High','not supported')))
        preset=empty_preset();preset['skill_bindings']=[dict(source='heavy_attack',stance='any',move='okatsu.charged_rush'),
            dict(source='heavy_attack',stance='high',move='okatsu.leaping_slash')]
        cases.append((preset,('High Heavy attack','Only one override','remove one row')))
        for source,stance,required in (('high_heavy_followup','low','High stance'),):
            preset=empty_preset();preset['skill_bindings']=[dict(source=source,stance=stance,move=sanada)]
            cases.append((preset,(config.SOURCE_LABELS[source],config.move_label(sanada),required,'Choose')))
        preset=empty_preset();preset['low_heavy']='jin_hayabusa.action_0c6e'
        preset['skill_bindings']=[dict(source='heavy_attack',stance='mid',move=preset['low_heavy'])]
        cases.append((preset,('Low Triangle / Y string','Mid Heavy attack','cannot share','Disable')))
        preset=empty_preset();preset['skill_bindings']=[dict(source='dodge_attack',stance='mid',move='jin_hayabusa.action_0c6f')]
        cases.append((preset,('Low Dodge attack','Low Triangle / Y string','Enable that string')))
        for preset,parts in cases:
            before=copy.deepcopy(preset)
            with self.subTest(parts=parts),self.assertRaises(ValueError) as caught:config.validate_preset(preset)
            for part in parts:self.assertIn(part,str(caught.exception))
            self.assertEqual(preset,before)
        preset=empty_preset();preset['stance_holds']['high']=launcher
        preset['skill_bindings']=[dict(source='guard_light',stance='high',move=launcher)]
        self.fixture(preset)

    def test_preview_rejects_slot_overflow_and_incomplete_selected_graphs(self):
        # Compile pending moves through the same path used by Desktop.preview before Save.
        # Cover native-slot expansion, phase capacity and missing native follow-up dependencies.
        # A valid source manifest alone cannot certify the final selected graph.
        preset=empty_preset();preset['skill_bindings']=[dict(source=source,stance=stance,move='okatsu.charged_rush')
            for source,stance in (('heavy_attack','any'),('tiger_sprint','any'),('dodge_attack','any'),
                                  ('guard_light','any'),('light_attack','low'),('high_heavy_followup','high'))]
        self.fixture(preset)
        preset['stance_holds']['low']='jin_hayabusa.action_0c79'
        self.fixture(preset)
        preset=empty_preset();preset.update(low_heavy='jin_hayabusa.action_0c6e',tap_move='jin_hayabusa.izuna_drop',
            hold_move='sanada_yukimura.action_0c6a',chord_stance='high')
        preset['stance_holds']['mid']='jin_hayabusa.action_0bbf'
        preset['frost_moon']=dict(low='jin_hayabusa.action_0c71',mid='jin_hayabusa.action_0c81',high='jin_hayabusa.action_0c75')
        preset['skill_bindings']=[dict(source='light_attack',stance='low',move='toyotomi_hideyori.action_0d30'),
            dict(source='guard_light',stance='mid',move='oda_nobunaga.action_0c6e'),
            dict(source='high_heavy_followup',stance='high',move='tachibana_muneshige.action_0d8d')]
        self.assertEqual(len(prepare.configured_imports(preset)['moves'])+len(prepare.configured_replacements(preset)['moves']),33)
        self.fixture(preset)
        preset['hold_move']=None;self.fixture(preset)
        preset=empty_preset();preset['tap_move']='jin_hayabusa.action_0c71'
        read=prepare.read_import_manifest
        def incomplete(path):
            # Remove one required phase after reading an otherwise valid source definition.
            # This models an incomplete selection rather than corrupting the recorded source bytes.
            # Preview must catch the missing dash dependency before native loading begins.
            manifest=read(path)
            if manifest['boss_id']=='jin_hayabusa':manifest['hold_chains'][preset['tap_move']].pop()
            return manifest
        with patch.object(prepare,'read_import_manifest',side_effect=incomplete),self.assertRaisesRegex(ValueError,'missing from the selected move sequence'):
            prepare.configured_replacements(preset)
        with patch.object(prepare,'check_import_topology',side_effect=ValueError('Unsupported source action family')), \
             self.assertRaisesRegex(ValueError,'selected move sequences are incompatible'):
            prepare.configured_replacements(preset)
