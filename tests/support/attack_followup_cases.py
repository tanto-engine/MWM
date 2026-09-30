"""Confirmed sword attacks can open stance-scoped follow-up inputs."""
import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'runtime'))
from engine_config import DEFAULT_PRESET, binding_for_preset, validate_preset
from game_controller import GAME_DEVICE, game_binding
from gestures import RoutedGesture


class AttackFollowupCases(unittest.TestCase):
    def binding(self, gesture='after_strong', stance='low'):
        value = copy.deepcopy(DEFAULT_PRESET)
        value['low_heavy'] = None
        value['skill_bindings'] = [dict(source='tiger_sprint', stance=stance,
            move='okatsu.charged_rush', input=dict(modifier_mask=0x100,
            trigger_mask=0x4000 if gesture == 'after_strong' else 0x8000,
            gesture=gesture))]
        value = validate_preset(value)
        calibration = dict(device=GAME_DEVICE, lb_mask=0x100)
        return game_binding(calibration, binding_for_preset(calibration, value,
            [dict(id='okatsu.charged_rush')]))

    def test_requires_confirmed_attack_and_fresh_followup_edge(self):
        calibration, binding = self.binding()
        gate = RoutedGesture(calibration, binding, 1000)
        gate.set_stance(2)
        gate.process(dict(kind='input_device', **GAME_DEVICE), 100)
        def send(mask, now):
            gate.process(dict(kind='input', backend='xinput', slot=0, buttons=mask,
                edge_basis='previous_observation'), now)
        def action(**changes):
            record = dict(actor='0x100000', native_result=1, valid_fields=20,
                          input_key=0xCF5, after_key=0xCF5, motion_key=4300,
                          after='0x300000', qpc=200)
            record.update(changes)
            gate.observe_action(record, 0x100000, 200, 38)
        send(0, 101)
        send(0x4100, 150)
        self.assertFalse(gate.fields(151)['armed'])
        send(0, 160)
        for changes in (dict(native_result=0), dict(actor='0x200000'),
                        dict(valid_fields=4), dict(motion_key=999),
                        dict(valid_fields=20 | (1 << 16))):
            action(**changes)
            send(0x4100, 210)
            self.assertFalse(gate.fields(211)['armed'])
            send(0, 220)
        action()
        gate.advance_attack(250, 0x300000, 37.9)
        send(0, 250)
        self.assertFalse(gate.fields(251)['armed'])
        gate.advance_attack(260, 0x300000, 38)
        send(0, 270)
        send(0x4100, 300)
        fields = gate.fields(301)
        self.assertTrue(fields['armed'])
        self.assertEqual(fields['chord_policy'], (1 << 36) | (1 << 32))
        self.assertEqual(fields['variant'], 0)
        gate.dispatched()
        send(0, 320)
        send(0x4100, 330)
        self.assertFalse(gate.fields(331)['armed'])

    def test_window_stance_and_occupied_inputs(self):
        calibration, binding = self.binding('after_quick', 'high')
        gate = RoutedGesture(calibration, binding, 1000)
        gate.set_stance(0)
        gate.process(dict(kind='input_device', **GAME_DEVICE), 100)
        gate.process(dict(kind='input', backend='xinput', slot=0, buttons=0,
            edge_basis='previous_observation'), 101)
        gate.observe_action(dict(actor='0x100000', native_result=1, valid_fields=20,
            input_key=0xCB3, after_key=0xCB3, motion_key=3100,
            after='0x300000', qpc=200), 0x100000, 200, 58)
        gate.advance_attack(200, 0x300000, 58)
        gate.process(dict(kind='input', backend='xinput', slot=0, buttons=0x8100,
            edge_basis='previous_observation'), 801)
        self.assertFalse(gate.fields(802)['armed'])
        for gesture, stance in (('after_strong', 'high'), ('after_quick', 'mid')):
            with self.assertRaisesRegex(ValueError, 'occupied'):
                self.binding(gesture, stance)

    def test_long_opener_waits_for_recovery_and_interruption_cancels(self):
        calibration, binding = self.binding()
        gate = RoutedGesture(calibration, binding, 1000)
        gate.set_stance(2)
        gate.process(dict(kind='input_device', **GAME_DEVICE), 100)
        def send(mask, now):
            gate.process(dict(kind='input', backend='xinput', slot=0, buttons=mask,
                edge_basis='previous_observation'), now)
        record = dict(actor='0x100000', native_result=1, valid_fields=20,
            input_key=0xCF5, after_key=0xCF5, motion_key=4300,
            after='0x300000', qpc=200)
        send(0, 101)
        gate.observe_action(record, 0x100000, 200, 38)
        gate.advance_attack(800, 0x300000, 37)
        send(0x4100, 810)
        self.assertFalse(gate.fields(811)['armed'])
        send(0, 820)
        gate.advance_attack(900, 0x300000, 38)
        send(0, 910)
        send(0x4100, 1000)
        self.assertTrue(gate.fields(1001)['armed'])
        gate.set_stance(1)
        self.assertFalse(gate.fields(1002)['armed'])
        gate.set_stance(2)
        gate.observe_action(record, 0x100000, 1100, 38)
        self.assertFalse(gate.attack_watch)
        record['qpc'] = 1200
        gate.observe_action(record, 0x100000, 1200, 38)
        gate.advance_attack(1210, 0x400000, 20)
        self.assertFalse(gate.attack_watch)

    def test_replaced_source_attack_cannot_offer_dead_followup(self):
        base = copy.deepcopy(DEFAULT_PRESET)
        available = copy.deepcopy(base)
        available['skill_bindings'].append(dict(source='tiger_sprint',stance='high',
            move='okatsu.charged_rush',input=dict(modifier_mask=0x100,
            trigger_mask=0x8000,gesture='after_quick')))
        self.assertEqual(validate_preset(available),available)
        for gesture, stance, source in (('after_strong','low','low_heavy'),
                                        ('after_strong','mid','heavy_attack'),
                                        ('after_quick','low','light_attack')):
            value = copy.deepcopy(base)
            value['skill_bindings'].append(dict(source='tiger_sprint',stance=stance,
                move='okatsu.charged_rush',input=dict(modifier_mask=0x100,
                trigger_mask=0x4000 if gesture=='after_strong' else 0x8000,
                gesture=gesture)))
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, 'replaced'):
                validate_preset(value)

    def test_held_strong_preserves_original_tap_followup(self):
        value = copy.deepcopy(DEFAULT_PRESET)
        value['skill_bindings'] = [row for row in value['skill_bindings']
                                   if (row['source'], row['stance']) != ('heavy_attack', 'mid')]
        value['stance_holds']['mid'] = 'oda_nobunaga.action_0c6e'
        value['skill_bindings'].append(dict(source='tiger_sprint', stance='mid',
            move='okatsu.leaping_slash', input=dict(modifier_mask=0x100,
            trigger_mask=0x4000, gesture='after_strong')))
        self.assertEqual(validate_preset(value), value)
        calibration = dict(device=GAME_DEVICE, lb_mask=0x100)
        _, binding = game_binding(calibration, binding_for_preset(calibration, value,
            [dict(id='oda_nobunaga.action_0c6e'), dict(id='okatsu.leaping_slash')]))
        self.assertEqual(binding['routes'][-1]['gesture'], 'after_strong')

    def test_native_followups_cover_every_stance_and_reject_strings(self):
        for source in ('guard_strong', 'strong_followup', 'quick_followup'):
            for stance in ('low', 'mid', 'high'):
                value = copy.deepcopy(DEFAULT_PRESET)
                value['skill_bindings'] = [dict(source=source, stance=stance, move='okatsu.charged_rush')]
                self.assertEqual(validate_preset(value), value)
                value['skill_bindings'][0]['move'] = 'toyotomi_hideyori.action_0d30'
                with self.subTest(source=source, stance=stance), self.assertRaisesRegex(ValueError, 'single skill'):
                    validate_preset(value)

    def test_legacy_alias_and_custom_followup_cannot_share_native_route(self):
        value = copy.deepcopy(DEFAULT_PRESET)
        value['skill_bindings'] = [dict(source='strong_followup', stance='high', move='okatsu.charged_rush'),
            dict(source='high_heavy_followup', stance='high', move='okatsu.leaping_slash')]
        with self.assertRaisesRegex(ValueError, 'Only one override'):
            validate_preset(value)
        value['skill_bindings'][0]['stance'] = 'low'
        value['skill_bindings'][1] = dict(source='tiger_sprint', stance='low', move='okatsu.leaping_slash',
            input=dict(modifier_mask=0x100, trigger_mask=0x4000, gesture='after_strong'))
        value['low_heavy'] = None
        with self.assertRaisesRegex(ValueError, 'already selects'):
            validate_preset(value)

    def test_custom_chord_cannot_silently_preempt_new_native_skill(self):
        value = copy.deepcopy(DEFAULT_PRESET)
        value.update(tap_move='okatsu.charged_rush', hold_move=None,
            modifier_mask=0x100, trigger_mask=0x8000, chord_stance='low')
        calibration = dict(device=GAME_DEVICE, lb_mask=0x100)
        for source in ('guard_strong', 'quick_followup'):
            value['skill_bindings'] = [dict(source=source, stance='low', move='okatsu.leaping_slash')]
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, 'overlaps a custom'):
                game_binding(calibration, binding_for_preset(calibration, value))
            value['chord_stance'] = 'high'
            game_binding(calibration, binding_for_preset(calibration, value))
            value['chord_stance'] = 'low'

    def test_one_graph_cannot_borrow_both_attack_continuation_families(self):
        value = copy.deepcopy(DEFAULT_PRESET); value['low_heavy'] = None
        move = 'jin_hayabusa.action_0c6e'
        value['skill_bindings'] = [dict(source=source, stance='low', move=move)
                                   for source in ('light_attack', 'heavy_attack')]
        with self.assertRaisesRegex(ValueError, 'Quick and Strong'):
            validate_preset(value)


if __name__ == '__main__':
    unittest.main()
