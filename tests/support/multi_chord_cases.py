"""Offline checks for independent custom inputs and native command publication."""
import copy
import ctypes as C
import json
from pathlib import Path
import struct
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'runtime'),str(ROOT/'mwm/app')]
from engine_config import DEFAULT_PRESET, binding_for_preset, move_capabilities, validate_preset
from game_controller import GAME_DEVICE, game_binding, saved_buttons
from gestures import RoutedGesture
from prepare_session import compiled_skill_bindings, compiled_chord_reservations
from run_dispatch import CommandMap
from trainer import remap_preset
from binding_groups import export_group, import_group
from web_worker import Desktop

DS4=json.loads((ROOT/'mwm/data/controller-calibration.json').read_text())
XBOX=dict(device=GAME_DEVICE,lb_mask=0x100)


def preset():
    value=copy.deepcopy(DEFAULT_PRESET)
    value['skill_bindings']=[dict(source='tiger_sprint',stance='low',move='okatsu.charged_rush',
        input=dict(modifier_mask=16,trigger_mask=4,gesture='tap')),
        dict(source='tiger_sprint',stance='low',move='okatsu.leaping_slash',
        input=dict(modifier_mask=16,trigger_mask=8,gesture='hold'))]
    return value


class MultiChordCases(unittest.TestCase):
    def test_two_button_custom_route_accepts_non_lb_modifier(self):
        value=copy.deepcopy(DEFAULT_PRESET)
        value['skill_bindings']=[dict(source='tiger_sprint',stance='low',move='okatsu.charged_rush',
            input=dict(modifier_mask=4,trigger_mask=1,gesture='tap'))]
        calibration,binding=game_binding(DS4,binding_for_preset(DS4,value,
            [dict(id=value['tap_move']),dict(id='okatsu.charged_rush')]))
        self.assertEqual((binding['routes'][-1]['modifier_mask'],binding['routes'][-1]['trigger_mask']),(0x2000,0x4000))
        gate=RoutedGesture(calibration,binding,1000)
        gate.set_stance(2);gate.process(dict(kind='input_device',**GAME_DEVICE),100)
        for buttons,now in ((0,101),(0x6000,200),(0x2000,220)):
            gate.process(dict(kind='input',backend='xinput',slot=0,buttons=buttons,
                              edge_basis='previous_observation'),now)
        self.assertEqual((gate.fields(221)['armed'],gate.fields(221)['variant']),(True,1))

    def test_charged_rush_shared_by_mid_frost_and_high_custom_input(self):
        value=copy.deepcopy(DEFAULT_PRESET)
        value['frost_moon']['mid']='okatsu.charged_rush'
        value['skill_bindings'].append(dict(source='tiger_sprint',stance='high',
            move='okatsu.charged_rush',input=dict(modifier_mask=16,trigger_mask=8,gesture='tap')))
        self.assertEqual(validate_preset(value)['skill_bindings'][-1]['move'],'okatsu.charged_rush')
        self.assertIn('okatsu.charged_rush',Desktop().preview(dict(preset=value,calibration=DS4))['moves'])

    def test_shared_graph_and_duplicate_frost_still_rejected(self):
        value=copy.deepcopy(DEFAULT_PRESET)
        value['frost_moon']['mid']='jin_hayabusa.action_0bc0'
        value['skill_bindings'].append(dict(source='tiger_sprint',stance='high',
            move='jin_hayabusa.action_0bc0',input=dict(modifier_mask=16,trigger_mask=8,gesture='tap')))
        with self.assertRaisesRegex(ValueError,'same stance across bindings'):
            validate_preset(value)
        value=copy.deepcopy(DEFAULT_PRESET)
        value['frost_moon']['low']=value['frost_moon']['mid']='okatsu.charged_rush'
        with self.assertRaisesRegex(ValueError,'different move in each stance'):
            validate_preset(value)

    def test_sequence_accepts_fresh_followup_while_first_is_held(self):
        value=copy.deepcopy(DEFAULT_PRESET)
        value['skill_bindings']=[dict(source='tiger_sprint',stance='low',move='okatsu.charged_rush',
            input=dict(modifier_mask=16,trigger_mask=4,followup_mask=8,gesture='sequence'))]
        calibration,binding=game_binding(DS4,binding_for_preset(DS4,value,
            [dict(id=value['tap_move']),dict(id='okatsu.charged_rush')]))
        gate=RoutedGesture(calibration,binding,1000)
        gate.set_stance(2);gate.process(dict(kind='input_device',**GAME_DEVICE),100)
        def send(mask,now):
            gate.process(dict(kind='input',backend='xinput',slot=0,buttons=mask,
                              edge_basis='previous_observation'),now)
        send(0,101);send(0x2100,200)
        staged=gate.fields(201)
        self.assertEqual((staged['reserve'],staged['chord_policy']),
                         (True,(1<<32)|(1<<35)|(0xA100<<16)))
        send(0xA100,250)
        self.assertEqual((gate.fields(251)['armed'],gate.chord_sequence),(True,1))
        gate.dispatched();send(0x2100,260);send(0xA100,270)
        self.assertFalse(gate.fields(271)['armed'])
        send(0,300);send(0x2100,400);send(0xA100,1001)
        self.assertFalse(gate.fields(1002)['armed'])
        send(0,1010);send(0x2100,1100);send(0xA100,1700)
        self.assertEqual((gate.fields(1701)['armed'],gate.chord_sequence),(True,2))

    def test_sequence_requires_a_later_observation_for_followup(self):
        value=copy.deepcopy(DEFAULT_PRESET)
        value['skill_bindings']=[dict(source='tiger_sprint',stance='low',move='okatsu.charged_rush',
            input=dict(modifier_mask=16,trigger_mask=4,followup_mask=8,gesture='sequence'))]
        calibration,binding=game_binding(DS4,binding_for_preset(DS4,value,
            [dict(id=value['tap_move']),dict(id='okatsu.charged_rush')]))
        for release_first in (False,True):
            gate=RoutedGesture(calibration,binding,1000)
            gate.set_stance(2);gate.process(dict(kind='input_device',**GAME_DEVICE),100)
            def send(mask,now):
                gate.process(dict(kind='input',backend='xinput',slot=0,buttons=mask,
                                  edge_basis='previous_observation'),now)
            send(0,101);send(0x2100,200)
            if release_first: send(0x100,200)
            send(0x8100 if release_first else 0xA100,200)
            self.assertFalse(gate.fields(201)['armed'])

    def test_reservations_cover_every_route_before_its_first_input_frame(self):
        value=preset()
        value['tap_move']='okatsu.charged_rush'
        value['hold_move']=None
        value['skill_bindings'][1]['input']['gesture']='tap'
        reservations=compiled_chord_reservations(value,DS4,[dict(id='okatsu.charged_rush'),
                                                        dict(id='okatsu.leaping_slash')])
        self.assertEqual(reservations,[dict(buttons=0x500,stances=1,mode=0),
            dict(buttons=0x2100,stances=1,mode=0),
            dict(buttons=0x8100,stances=1,mode=0)])

    def test_reservations_skip_attack_followup_and_include_sequence_start(self):
        value=copy.deepcopy(DEFAULT_PRESET)
        value['skill_bindings']=[dict(source='tiger_sprint',stance='low',move='okatsu.charged_rush',
            input=dict(modifier_mask=16,trigger_mask=4,followup_mask=8,gesture='sequence')),
            dict(source='tiger_sprint',stance='high',move='okatsu.charged_rush',
            input=dict(modifier_mask=16,trigger_mask=8,gesture='after_quick'))]
        reservations=compiled_chord_reservations(value,DS4,[dict(id=value['tap_move']),
            dict(id='okatsu.charged_rush')])
        self.assertEqual(reservations,[dict(buttons=0x500,stances=1,mode=0),
            dict(buttons=0x2100,stances=1,mode=10)])

    def test_custom_hold_string_stays_held_and_unlatched_for_chain(self):
        value=copy.deepcopy(DEFAULT_PRESET)
        value['string_enabled']=True
        value['skill_bindings']=[dict(source='tiger_sprint',stance='low',
            move='okatsu.action_0c61',input=dict(modifier_mask=16,trigger_mask=4,gesture='hold'))]
        calibration,binding=game_binding(DS4,binding_for_preset(DS4,value,
            [dict(id='okatsu.charged_rush'),dict(id='okatsu.leaping_slash'),dict(id='okatsu.action_0c61')]))
        gate=RoutedGesture(calibration,binding,1000,string_variant=2)
        gate.set_stance(2);gate.process(dict(kind='input_device',**GAME_DEVICE),100)
        def send(mask,now):
            gate.process(dict(kind='input',backend='xinput',slot=0,buttons=mask,
                              edge_basis='previous_observation',axes=dict(lt=0,rt=0)),now)
        send(0,101);send(0x2100,200)
        fields=gate.fields(450)
        self.assertEqual((fields['armed'],fields['held'],fields['latched'],fields['variant']),
                         (True,True,0,2))
        owned=C.create_string_buffer(224)
        command=CommandMap.__new__(CommandMap)
        command.address,command.sequence=C.addressof(owned),0
        config=dict(generation=7,player=0x100000,owner=0x200000,vtable=0x300000,
                    banks=[0x400000,0x500000,0x600000],imports=[dict(descriptor=0x700000+i,
                    payload=0x800000+i,key=0xC60+i,motion=1200+i) for i in range(3)])
        command.publish(config,**fields)
        self.assertEqual(struct.unpack_from('<3Q',owned.raw,64+128),
                         (fields['chord_policy'],2,0))
        gate.dispatched()
        continued=gate.fields(451)
        self.assertEqual((continued['armed'],continued['held'],continued['latched']),
                         (False,True,0))
        command.publish(config,**continued)
        self.assertEqual(struct.unpack_from('<3Q',owned.raw,64+128),(0,2,0))
        send(0x100,500)
        self.assertFalse(gate.fields(501)['held'])

    def test_sequence_requires_order_and_preserves_original_input(self):
        value=copy.deepcopy(DEFAULT_PRESET)
        value['skill_bindings']=[dict(source='tiger_sprint',stance='low',move='okatsu.charged_rush',
            input=dict(modifier_mask=16,trigger_mask=4,followup_mask=8,gesture='sequence')),
            dict(source='tiger_sprint',stance='low',move='okatsu.leaping_slash',
            input=dict(modifier_mask=16,trigger_mask=8,gesture='tap'))]
        imports=[dict(id=value['tap_move']),dict(id='okatsu.charged_rush'),dict(id='okatsu.leaping_slash')]
        calibration,binding=game_binding(DS4,binding_for_preset(DS4,value,imports))
        self.assertEqual(binding['routes'][1]['followup_mask'],0x8000)
        gate=RoutedGesture(calibration,binding,1000)
        gate.set_stance(2)
        gate.process(dict(kind='input_device',**GAME_DEVICE),100)
        def send(mask,now):
            gate.process(dict(kind='input',backend='xinput',slot=0,buttons=mask,
                              edge_basis='previous_observation'),now)
        send(0,101)
        send(0x100|0x2000|0x8000,200)
        self.assertFalse(gate.fields(221)['armed'])
        send(0,230)
        send(0x100|0x2000,240)
        send(0x100,250)
        staged=gate.fields(251)
        self.assertEqual((staged['reserve'],staged['chord_policy']),
                         (True,(1<<32)|(1<<35)|(0x8100<<16)))
        send(0x100|0x8000,300)
        fields=gate.fields(301)
        self.assertEqual((fields['armed'],fields['variant']),(True,1))
        self.assertEqual(fields['chord_policy']>>16&0xffff,0)
        self.assertEqual(fields['chord_policy'],(1<<35)|(1<<32))
        send(0x100,320)
        self.assertEqual((gate.fields(321)['variant'],gate.chord_sequence),(1,1))
        owned=C.create_string_buffer(224)
        command=CommandMap.__new__(CommandMap)
        command.address,command.sequence=C.addressof(owned),0
        config=dict(generation=7,player=0x100000,owner=0x200000,vtable=0x300000,
                    banks=[0x400000,0x500000,0x600000],imports=[dict(descriptor=0x700000+i,
                    payload=0x800000+i,key=0xC60+i,motion=1200+i) for i in range(3)])
        command.publish(config,**fields)
        self.assertEqual(struct.unpack_from('<3Q',owned.raw,64+128),
                         (fields['chord_policy']|1,1,0))

    def test_sequence_window_release_reconnect_and_stance_invalidation(self):
        value=copy.deepcopy(DEFAULT_PRESET)
        value['skill_bindings']=[dict(source='tiger_sprint',stance='low',move='okatsu.charged_rush',
            input=dict(modifier_mask=16,trigger_mask=4,followup_mask=8,gesture='sequence'))]
        calibration,binding=game_binding(DS4,binding_for_preset(DS4,value,
            [dict(id=value['tap_move']),dict(id='okatsu.charged_rush')]))
        def make():
            gate=RoutedGesture(calibration,binding,1000)
            gate.set_stance(2)
            gate.process(dict(kind='input_device',**GAME_DEVICE),100)
            send(gate,0,101)
            return gate
        def send(gate,mask,now,edge='previous_observation'):
            gate.process(dict(kind='input',backend='xinput',slot=0,buttons=mask,edge_basis=edge),now)
        for followup,expected in ((850,True),(851,False)):
            gate=make();send(gate,0x2100,200);send(gate,0x100,250)
            send(gate,0x8100,followup)
            self.assertEqual(gate.fields(followup+1)['armed'],expected)
        gate=make();send(gate,0x2100,200);send(gate,0x100,250)
        send(gate,0,300);send(gate,0x8100,320)
        self.assertFalse(gate.fields(321)['armed'])
        gate=make();send(gate,0x2100,200);send(gate,0x100,250)
        gate.process(dict(kind='input_unavailable',backend='xinput',slot=0),300)
        gate.process(dict(kind='input_device',**GAME_DEVICE),310)
        send(gate,0x8100,320)
        self.assertFalse(gate.fields(321)['armed'])
        gate=make();send(gate,0x2100,200);send(gate,0x100,250)
        gate.set_stance(1);gate.set_stance(2);send(gate,0x8100,320)
        self.assertFalse(gate.fields(321)['armed'])
        gate=make();send(gate,0x2100,200);send(gate,0x100,250);send(gate,0x8100,320)
        self.assertTrue(gate.fields(321)['armed'])
        send(gate,0,330)
        self.assertFalse(gate.fields(331)['armed'])

    def test_sequence_schema_conflicts_and_controller_mapping(self):
        value=copy.deepcopy(DEFAULT_PRESET)
        value['skill_bindings']=[dict(source='tiger_sprint',stance='low',move='okatsu.charged_rush',
            input=dict(modifier_mask=16,trigger_mask=4,followup_mask=8,gesture='sequence'))]
        self.assertEqual(validate_preset(value),value)
        mapped=remap_preset(value,DS4,XBOX)
        self.assertEqual(mapped['skill_bindings'][0]['input'],dict(
            modifier_mask=0x100,trigger_mask=0x2000,followup_mask=0x8000,gesture='sequence'))
        alternative=copy.deepcopy(value)
        alternative['skill_bindings'][0]['input'].update(modifier_mask=4,trigger_mask=8,followup_mask=16)
        calibration,binding=game_binding(DS4,binding_for_preset(DS4,alternative,
            [dict(id=value['tap_move']),dict(id='okatsu.charged_rush')]))
        gate=RoutedGesture(calibration,binding,1000)
        gate.set_stance(2);gate.process(dict(kind='input_device',**GAME_DEVICE),100)
        for buttons,now in ((0,101),(0xA000,200),(0x2000,250),(0x2100,300)):
            gate.process(dict(kind='input',backend='xinput',slot=0,buttons=buttons,
                              edge_basis='previous_observation'),now)
        self.assertEqual((gate.fields(301)['armed'],gate.fields(301)['variant']),(True,1))
        for input in (dict(modifier_mask=16,trigger_mask=4,followup_mask=4,gesture='sequence'),
                      dict(modifier_mask=16,trigger_mask=4,gesture='sequence')):
            bad=copy.deepcopy(value);bad['skill_bindings'][0]['input']=input
            with self.assertRaises(ValueError): validate_preset(bad)
        bad=copy.deepcopy(value)
        bad['skill_bindings'].append(dict(source='tiger_sprint',stance='low',move='okatsu.leaping_slash',
            input=dict(modifier_mask=16,trigger_mask=4,gesture='tap')))
        with self.assertRaisesRegex(ValueError,'sequence start'):
            validate_preset(bad)
        for key,mask in (('modifier_mask',32),('trigger_mask',32),('followup_mask',32),('followup_mask',2)):
            bad=copy.deepcopy(value);bad['skill_bindings'][0]['input'][key]=mask
            with self.assertRaises(ValueError): game_binding(DS4,binding_for_preset(DS4,bad))

    def test_same_pair_routes_by_stance_and_change_drops_pending_tap(self):
        value=preset()
        value['skill_bindings'][1]['stance']='mid'
        value['skill_bindings'][1]['input'].update(trigger_mask=4,gesture='tap')
        value=validate_preset(value)
        imports=[dict(id=value['tap_move']),dict(id='okatsu.charged_rush'),dict(id='okatsu.leaping_slash')]
        calibration,binding=game_binding(DS4,binding_for_preset(DS4,value,imports))
        gate=RoutedGesture(calibration,binding,1000)
        gate.set_stance(2)
        gate.process(dict(kind='input_device',**GAME_DEVICE),100)
        def send(mask,now):
            gate.process(dict(kind='input',backend='xinput',slot=0,buttons=mask,
                              edge_basis='previous_observation'),now)
        send(0,101);send(0x100|0x2000,200);send(0x100,240)
        self.assertEqual((gate.fields(241)['variant'],gate.chord_sequence),(1,1))
        gate.set_stance(1)
        self.assertFalse(gate.fields(242)['armed'])
        send(0x100|0x2000,250)
        self.assertFalse(gate.fields(251)['armed'])
        send(0x100,260);send(0x100|0x2000,300);send(0x100,340)
        self.assertEqual((gate.fields(341)['variant'],gate.chord_sequence),(2,2))
        gate.set_stance(None)
        self.assertEqual((gate.fields(342)['armed'],gate.fields(342)['chord_policy']),(False,0))

    def test_two_chords_publish_distinct_moves_and_global_sequence(self):
        value=preset()
        value['hold_move']='okatsu.leaping_slash'
        value=validate_preset(value)
        imports=[dict(id=value['tap_move']),dict(id='okatsu.charged_rush'),dict(id='okatsu.leaping_slash')]
        calibration,binding=game_binding(DS4,binding_for_preset(DS4,value,imports))
        gate=RoutedGesture(calibration,binding,1000)
        gate.set_stance(2)
        gate.process(dict(kind='input_device',**GAME_DEVICE),100)
        def send(mask,now):
            gate.process(dict(kind='input',backend='xinput',slot=0,buttons=mask,
                              edge_basis='previous_observation'),now)
        send(0,101)
        send(0x100|0x2000,200)
        first=gate.fields(201)
        self.assertTrue(first['reserve'])
        self.assertEqual(first['chord_policy'],((0x100|0x2000)<<16)|(1<<32))
        send(0x100,240)
        first=gate.fields(241)
        self.assertEqual((first['armed'],first['variant'],first['chord_sequence']),(True,1,1))
        gate.dispatched()
        self.assertFalse(gate.fields(242)['reserve'])
        send(0x100|0x8000,300)
        second=gate.fields(550)
        self.assertEqual((second['armed'],second['variant'],second['chord_sequence']),(True,2,2))
        self.assertEqual(second['chord_policy'],((0x100|0x8000)<<16)|(1<<32))
        owned=C.create_string_buffer(224)
        command=CommandMap.__new__(CommandMap)
        command.address,command.sequence=C.addressof(owned),0
        config=dict(generation=7,player=0x100000,owner=0x200000,vtable=0x300000,
                    banks=[0x400000,0x500000,0x600000],imports=[dict(descriptor=0x700000+i,
                    payload=0x800000+i,key=0xC60+i,motion=1200+i) for i in range(3)])
        command.publish(config,**second)
        self.assertEqual(struct.unpack_from('<Q',owned.raw,64+32)[0],2)
        self.assertEqual(struct.unpack_from('<3Q',owned.raw,64+128),(second['chord_policy']|1,2,0))
        gate.dispatched()
        send(0x100,600)
        send(saved_buttons(GAME_DEVICE,0x100,127,0),650)
        send(saved_buttons(GAME_DEVICE,0x100,128,0),700)
        self.assertTrue(gate.fields(701)['reserve'])
        send(saved_buttons(GAME_DEVICE,0x100,127,0),740)
        analog=gate.fields(741)
        self.assertEqual((analog['armed'],analog['variant'],analog['chord_sequence']),(True,0,3))
        self.assertEqual(analog['chord_policy'],((0x100|0x400)<<16)|(1<<32))
        gate.dispatched()
        send(saved_buttons(GAME_DEVICE,0x100,128,0),800)
        global_hold=gate.fields(1050)
        self.assertEqual((global_hold['armed'],global_hold['variant'],global_hold['chord_sequence']),(True,2,4))
        self.assertEqual(global_hold['chord_policy'],analog['chord_policy'])
        gate.dispatched()
        self.assertFalse(gate.fields(1051)['reserve'])

    def test_native_source_is_not_replaced_and_conflicts_are_rejected(self):
        value=preset()
        self.assertEqual(compiled_skill_bindings(value,[dict(id='okatsu.charged_rush')]),[])
        duplicate=copy.deepcopy(value)
        duplicate['skill_bindings'][1]['input'].update(trigger_mask=4,gesture='tap')
        with self.assertRaisesRegex(ValueError,'already selects'):
            validate_preset(duplicate)
        reversed_pair=copy.deepcopy(value)
        reversed_pair['skill_bindings'][1]['input'].update(modifier_mask=4,trigger_mask=16)
        with self.assertRaisesRegex(ValueError,'reversed'):
            validate_preset(reversed_pair)
        special=copy.deepcopy(value)
        special['skill_bindings'][0]['move']='jin_hayabusa.action_0c6f'
        with self.assertRaisesRegex(ValueError,'cannot use a custom input'):
            validate_preset(special)
        value['skill_bindings'][1]['input'].update(trigger_mask=4,gesture='hold')
        self.assertEqual(validate_preset(value),value)
        self.assertEqual(move_capabilities()['custom_binding_limit'],24)
        unsupported=copy.deepcopy(value)
        unsupported['skill_bindings'][0]['input'].update(modifier_mask=2,trigger_mask=4)
        with self.assertRaisesRegex(ValueError,'two distinct'):
            game_binding(DS4,binding_for_preset(DS4,unsupported))

    def test_portable_custom_masks_in_moveset_and_skill_group(self):
        value=preset()
        mapped=remap_preset(value,DS4,XBOX)
        self.assertEqual([(r['input']['modifier_mask'],r['input']['trigger_mask']) for r in mapped['skill_bindings']],
                         [(0x100,0x2000),(0x100,0x8000)])
        group=export_group(value,DS4,'skills')
        self.assertIn('controller',group)
        imported=import_group(group,mapped,XBOX,'skills')
        self.assertEqual(imported['skill_bindings'],mapped['skill_bindings'])
        legacy=export_group(DEFAULT_PRESET,DS4,'skills')
        self.assertNotIn('controller',legacy)
        self.assertEqual(import_group(legacy,DEFAULT_PRESET,DS4,'skills'),DEFAULT_PRESET)
        group['controller']['button_map']={'16':0x100}
        with self.assertRaises(ValueError): import_group(group,mapped,XBOX,'skills')

    def test_custom_add_override_can_share_an_occupied_native_source(self):
        value=copy.deepcopy(DEFAULT_PRESET)
        value['skill_bindings'].append(dict(source='tiger_sprint',stance='low',move='okatsu.charged_rush'))
        added=Desktop().add_override(dict(calibration=DS4,preset=value,mode='custom'))
        self.assertEqual(added['skill_bindings'][-1]['source'],'tiger_sprint')
        self.assertIn('input',added['skill_bindings'][-1])
        self.assertEqual(len(compiled_skill_bindings(added,[dict(id=row['move']) for row in added['skill_bindings']]
                         +[dict(id=move) for move in added['stance_holds'].values() if move])),
                         len(compiled_skill_bindings(value,[dict(id=row['move']) for row in value['skill_bindings']]
                         +[dict(id=move) for move in value['stance_holds'].values() if move])))
        original=Desktop().add_override(dict(calibration=DS4,preset=preset()))
        self.assertEqual((original['skill_bindings'][-1]['source'],original['skill_bindings'][-1]['stance']),
                         ('tiger_sprint','low'))
        self.assertNotIn('input',original['skill_bindings'][-1])


if __name__=='__main__': unittest.main()
