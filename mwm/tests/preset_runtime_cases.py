"""Offline preset persistence and live-switch safety checks."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'app'))
import web_worker as worker


class PresetRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.calibration = json.loads((ROOT/'data/controller-calibration.json').read_text(encoding='utf8'))
        self.first = json.loads((ROOT/'data/presets/sword-rebuild-1-supported.json').read_text(encoding='utf8'))
        self.second = deepcopy(self.first)
        self.second['name'] = 'Second saved preset'

    def seed(self, runtime, desktop):
        worker.atomic_json(runtime/'controller-calibration.json', self.calibration)
        worker.atomic_json(runtime/'controller-binding.json', self.first)
        params = dict(runtime=str(runtime), calibration=self.calibration)
        first = desktop.preset_save(dict(params, preset=self.first))['presets'][0]['id']
        second = desktop.preset_save(dict(params, preset=self.second))['presets'][1]['id']
        return params, first, second

    def test_library_load_is_controller_aware_and_preserves_dirty_draft(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = Path(folder)
            with patch.object(worker.Desktop, 'location', return_value=runtime), patch.object(worker, 'process_matches', return_value=False):
                desktop = worker.Desktop()
                params, first, second = self.seed(runtime, desktop)
                listing = desktop.preset_list()
                self.assertEqual(([item['id'] for item in listing['presets']], listing['selected_id']), ([first, second], first))
                with self.assertRaisesRegex(ValueError, 'Unsaved edits'):
                    desktop.preset_load(dict(params, id=second, dirty=True))
                self.assertEqual(desktop.preset_load(dict(params, id=second, dirty=True, discard_draft=True)), self.second)
                self.assertEqual(worker.read_json(runtime/'controller-binding.json'), self.first)
                xinput = desktop.xinput_calibration(0)
                loaded = desktop.preset_load(dict(params, id=second, calibration=xinput))
                self.assertEqual((loaded['modifier_mask'], loaded['trigger_mask']), (0x100, 0x400))
                self.assertTrue(desktop.preset_list()['hotkey']['supported'])
                switched = desktop.preset_switch(dict(params, id=second))
                self.assertEqual(switched['presets']['selected_id'], second)
                self.assertEqual(worker.read_json(runtime/'controller-binding.json'), self.second)
                desktop.preset_delete(dict(params, id=second))
                self.assertEqual([item['id'] for item in desktop.preset_list()['presets']], [first])

    def test_first_library_view_adopts_existing_active_preset(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = Path(folder)
            worker.atomic_json(runtime/'controller-calibration.json', self.calibration)
            worker.atomic_json(runtime/'controller-binding.json', self.first)
            with patch.object(worker.Desktop, 'location', return_value=runtime), \
                 patch.object(worker, 'process_matches', return_value=False):
                desktop = worker.Desktop()
                first = desktop.preset_list()
                again = desktop.preset_list()
                self.assertEqual(first, again)
                self.assertEqual(first['selected_id'], first['presets'][0]['id'])
                self.assertEqual(first['presets'][0]['speed_overrides'], len(self.first['move_settings']))
                self.assertTrue((runtime/'moveset-library.json').is_file())

    def test_invalid_draft_never_changes_library(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = Path(folder)
            with patch.object(worker.Desktop, 'location', return_value=runtime), patch.object(worker, 'process_matches', return_value=False):
                desktop = worker.Desktop()
                params, _, _ = self.seed(runtime, desktop)
                before = (runtime/'moveset-library.json').read_bytes()
                bad = deepcopy(self.second)
                bad['modifier_mask'] = 3
                with self.assertRaises(ValueError):
                    desktop.preset_save(dict(params, preset=bad))
                self.assertEqual((runtime/'moveset-library.json').read_bytes(), before)

    def test_library_save_while_running_does_not_change_active_binding(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = Path(folder)
            running = {'value': False}
            with patch.object(worker.Desktop, 'location', return_value=runtime), \
                 patch.object(worker, 'process_matches', side_effect=lambda _: running['value']):
                desktop = worker.Desktop()
                params, _, _ = self.seed(runtime, desktop)
                third = deepcopy(self.first)
                third['name'] = 'Saved during play'
                running['value'] = True
                desktop.preset_save(dict(params, preset=third))
                self.assertEqual(worker.read_json(runtime/'controller-binding.json'), self.first)
                self.assertEqual(len(desktop.preset_list()['presets']), 3)

    def test_live_cycle_waits_for_clean_stop_before_writing_or_restarting(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = Path(folder)
            live = {'running': False, 'stops': 0, 'starts': 0}
            def disable():
                self.assertEqual(worker.read_json(runtime/'controller-binding.json'), self.first)
                live['stops'] += 1
                live['running'] = False
                worker.atomic_json(runtime/'play-status.json', dict(state='stopped'))
            def launch():
                self.assertEqual(worker.read_json(runtime/'controller-binding.json'), self.second)
                live['starts'] += 1
                return object()
            with patch.object(worker.Desktop, 'location', return_value=runtime), \
                 patch.object(worker, 'process_matches', side_effect=lambda _: live['running']), \
                 patch.object(worker, 'active_runtime', return_value=None), \
                 patch.object(worker.trainer, 'disable_engine', side_effect=disable), \
                 patch.object(worker.trainer, 'launch_engine', side_effect=launch), \
                 patch.object(worker.trainer, 'RUNTIME', runtime):
                desktop = worker.Desktop()
                _, first, second = self.seed(runtime, desktop)
                worker.atomic_json(runtime/'play-status.json', dict(state='enabled'))
                live['running'] = True
                result = desktop.preset_cycle()
                self.assertEqual((live['stops'], live['starts']), (1, 1))
                self.assertEqual(result['presets']['selected_id'], second)
                self.assertNotEqual(first, second)

    def test_editor_cycle_rejects_stale_runtime(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = Path(folder)
            with patch.object(worker.Desktop, 'location', return_value=runtime), \
                 patch.object(worker, 'process_matches', return_value=False):
                desktop = worker.Desktop()
                self.seed(runtime, desktop)
                with self.assertRaisesRegex(ValueError, 'Active Engine changed'):
                    desktop.preset_cycle(dict(runtime=str(runtime/'stale')))
                self.assertEqual(worker.read_json(runtime/'controller-binding.json'), self.first)

    def test_cleanup_failure_leaves_old_binding_and_mod_stopped(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = Path(folder)
            live = {'running': False}
            def disable():
                live['running'] = False
                worker.atomic_json(runtime/'play-status.json', dict(state='cleanup_needs_attention'))
            with patch.object(worker.Desktop, 'location', return_value=runtime), \
                 patch.object(worker, 'process_matches', side_effect=lambda _: live['running']), \
                 patch.object(worker, 'active_runtime', return_value=None), \
                 patch.object(worker.trainer, 'disable_engine', side_effect=disable), \
                 patch.object(worker.trainer, 'launch_engine') as launch:
                desktop = worker.Desktop()
                self.seed(runtime, desktop)
                live['running'] = True
                with self.assertRaisesRegex(RuntimeError, 'safe cleanup'):
                    desktop.preset_cycle()
                self.assertEqual(worker.read_json(runtime/'controller-binding.json'), self.first)
                launch.assert_not_called()

    def test_cleanup_timeout_does_not_write_next_preset(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = Path(folder)
            with patch.object(worker.Desktop, 'location', return_value=runtime), \
                 patch.object(worker, 'process_matches', return_value=False):
                desktop = worker.Desktop()
                params, _, second = self.seed(runtime, desktop)
            with patch.object(worker.Desktop, 'location', return_value=runtime), \
                 patch.object(worker, 'process_matches', return_value=True), \
                 patch.object(worker, 'active_runtime', return_value=None), \
                 patch.object(worker.trainer, 'disable_engine') as disable, \
                 patch.object(worker.trainer, 'launch_engine') as launch, \
                 patch.object(worker.time, 'monotonic', side_effect=[0, 31]):
                with self.assertRaisesRegex(RuntimeError, 'timed out'):
                    desktop.preset_switch(dict(params, id=second))
                disable.assert_called_once()
                launch.assert_not_called()
                self.assertEqual(worker.read_json(runtime/'controller-binding.json'), self.first)

    def test_touchpad_requires_distinct_clean_press_release_press(self):
        detector = worker.TouchpadDoubleTap()
        def event(t, buttons, pressed, released, basis='previous_observation'):
            return dict(kind='input', observed_monotonic=t, buttons=buttons,
                        pressed_mask=pressed, released_mask=released, edge_basis=basis)
        self.assertFalse(detector.feed(event(0, 0x2000, None, None, 'unknown')))
        self.assertFalse(detector.feed(event(.1, 0, 0, 0x2000)))
        self.assertFalse(detector.feed(event(1, 0x2000, 0x2000, 0)))
        self.assertFalse(detector.feed(event(1.1, 0, 0, 0x2000)))
        self.assertTrue(detector.feed(event(1.3, 0x2000, 0x2000, 0)))
        self.assertFalse(detector.feed(event(1.35, 0, 0, 0x2000)))
        self.assertFalse(detector.feed(event(1.5, 0x2000, 0x2000, 0)))
        self.assertFalse(worker.Desktop.hotkey_capability(dict(device=dict(backend='xinput', slot=0)))['supported'])

    def test_hotkey_ignores_xinput_duplicate(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = Path(folder)
            worker.atomic_json(runtime/'controller-calibration.json', self.calibration)
            worker.atomic_json(runtime/'play-status.json', dict(state='enabled'))
            device = self.calibration['device']
            def input_event(t, buttons, pressed, released, basis='previous_observation'):
                return dict(kind='input', backend='winmm', slot=device['slot'], observed_monotonic=t,
                            buttons=buttons, pressed_mask=pressed, released_mask=released, edge_basis=basis)
            events = [
                [dict(kind='input_device', backend='winmm', slot=device['slot'],
                      manufacturer=device['manufacturer'], product=device['product'], num_buttons=14),
                 input_event(0, 0, None, None, 'unknown')],
                [input_event(.1, 0x2000, 0x2000, 0)],
                [input_event(.2, 0, 0, 0x2000)],
                [input_event(.3, 0x2000, 0x2000, 0)],
            ]
            class Reader:
                def __init__(self, duplicate):
                    self.events = [list(batch) for batch in events]
                    if duplicate:
                        self.events[-1].append(dict(kind='input', backend='xinput', slot=0,
                            observed_monotonic=.3, buttons=0x20 if duplicate == 'button' else 0,
                            pressed_mask=0x20 if duplicate == 'button' else 0,
                            logical_buttons=0x400 if duplicate == 'trigger' else 0))
                def poll(self):
                    return self.events.pop(0)
            with patch.object(worker.Desktop, 'location', return_value=runtime), \
                 patch.object(worker, 'process_matches', return_value=True):
                for duplicate in ('button', 'trigger', None):
                    reader = Reader(duplicate)
                    with patch.object(worker, 'ControllerReader', return_value=reader):
                        desktop = worker.Desktop()
                        self.assertEqual([desktop.preset_hotkey_poll() for _ in range(4)],
                                         [False, False, False, duplicate is None])


if __name__ == '__main__':
    unittest.main()
