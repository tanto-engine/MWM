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
    return dict(copy.deepcopy(config.DEFAULT_PRESET),tap_move=None,hold_move=None,low_heavy=None,
        stance_holds=dict(low=None,mid=None,high=None),frost_moon=dict(low=None,mid=None,high=None),
        skill_bindings=[],okatsu_grapple=False,mid_light_ender=False,string_enabled=False,move_settings={})


class CapabilityTests(unittest.TestCase):
    def fixture(self,preset):
        fixture=sessions.RuntimeSessionTests();fixture.setUp();fixture.configured_fixture(preset)
        return fixture,encode_session(fixture.config,fixture.pid,fixture.born)

    def test_reviewed_graphs_compile_for_every_chord_stance_and_frost_destination(self):
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

    def test_speed_and_developer_pulse_reach_graph_phases_and_abi(self):
        preset=empty_preset();preset['tap_move']='jin_hayabusa.action_0c71'
        preset['move_settings']={preset['tap_move']:dict(speed=.5)}
        fixture,_=self.fixture(preset)
        policy=dict(schema_version=1,moves={preset['tap_move']:dict(ki_pulse=dict(percent=65,fill_frames=18,hold_frames=35))})
        fixture.config['move_settings']=prepare.compiled_move_settings(preset,fixture.config['imports'],policy)
        encoded=encode_session(fixture.config,fixture.pid,fixture.born)
        for i,move in enumerate(fixture.config['imports']):
            expected=(.5,65,18,35,0) if move['id'].startswith('jin_hayabusa.') else (1.,40,25,24,0)
            self.assertEqual(MOVE_SETTINGS.unpack_from(encoded,5752+i*MOVE_SETTINGS.size),expected)
        self.assertEqual(struct.unpack_from('<II',encoded,6136),(0,0))

    def test_public_settings_reject_private_fields_and_frame_cuts(self):
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
        preset=empty_preset();preset['skill_bindings']=[dict(source='heavy_attack',stance='any',move='okatsu.charged_rush')]
        fixture,encoded=self.fixture(preset)
        self.assertEqual([(b['key'],b['stances']) for b in fixture.config['skill_bindings']],[(0xCF5,1),(0xC7A,2),(0xCB7,4)])
        for selection in range(5):
            fixture.config['controller_selection']=selection
            encoded=encode_session(fixture.config,fixture.pid,fixture.born)
            self.assertEqual(struct.unpack_from('<I',encoded,6136)[0],selection)
        for selection in (5,-1,True):
            with self.assertRaises(ValueError):
                encode_session(dict(fixture.config,controller_selection=selection),fixture.pid,fixture.born)

    def test_capabilities_exclude_unreviewed_recordings_and_migration_keeps_bindings(self):
        caps=config.move_capabilities();moves={m['id']:m for m in caps['moves']}
        self.assertEqual({m['id'] for m in caps['moves'] if m['chord']},set(config.CHORD_MOVES))
        self.assertFalse(moves['jin_hayabusa.action_03b2']['speed'])
        self.assertTrue(moves['jin_hayabusa.action_0c6f']['native'])
        self.assertNotIn('jin_hayabusa.action_0cac',moves)
        old=dict(config.DEFAULT_PRESET,schema_version=7,frost_startup_speed=2,frost_window_seconds=.75)
        old.pop('move_settings');old.pop('chord_stance')
        self.assertEqual(config.validate_preset(old),config.DEFAULT_PRESET)
        self.assertEqual(old['frost_startup_speed'],2)

    def test_frost_shared_import_retains_one_stance_owner(self):
        preset=empty_preset();move='okatsu.charged_rush'
        preset['frost_moon']['high']=move
        preset['skill_bindings']=[dict(source='tiger_sprint',stance='any',move=move)]
        with self.assertRaisesRegex(ValueError,'same stance'): config.validate_preset(preset)
        preset['skill_bindings'][0]['stance']='high'
        fixture,_=self.fixture(preset)
        fixture.config['skill_bindings'][0]['stances']=7
        with self.assertRaisesRegex(ValueError,'stance ownership'):
            encode_session(fixture.config,fixture.pid,fixture.born)

    def test_recording_metadata_cannot_promote_native_sources_or_moves(self):
        from catalogue import load_catalogue
        catalogue=load_catalogue();before=config.move_capabilities()
        catalogue['moves'].append(dict(id='unreviewed.captured_action',name='New recording',
            implementation=dict(selectable=True)))
        with patch('catalogue.load_catalogue',return_value=catalogue):
            self.assertEqual(config.move_capabilities(),before)
        self.assertEqual({source['id'] for source in before['native_sources']},
            {'tiger_sprint','dodge_attack','heavy_attack','guard_light'})
        for source,move in (('captured_native_skill','okatsu.charged_rush'),('tiger_sprint','unreviewed.captured_action')):
            preset=empty_preset();preset['skill_bindings']=[dict(source=source,stance='mid',move=move)]
            with self.assertRaisesRegex(ValueError,'Unsupported skill binding'):
                config.validate_preset(preset)
