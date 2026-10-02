"""Exercise the actual desktop pipe without controller or game access."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'app'), str(ROOT.parent/'runtime')]
import web_worker as worker


class DesktopProtocolTests(unittest.TestCase):
    def test_nonfinite_numbers_reject_before_dispatch_and_leave_pipe_usable(self):
        for token in ('NaN', 'Infinity', '-Infinity', '1e999'):
            with self.subTest(number=token), tempfile.TemporaryDirectory() as folder:
                requests = ['{"id":'+token+',"method":"snapshot"}',
                    '{"id":2,"method":"snapshot","params":{"nested":['+token+']}}']
                identifiers = [3, 4.5, 'next']
                requests += [json.dumps(dict(id=value, method='snapshot')) for value in identifiers]
                result = subprocess.run([sys.executable, '-B', str(ROOT/'tests/desktop_worker_fixture.py'), folder],
                    input='\n'.join(requests)+'\n', capture_output=True, text=True, encoding='utf8', timeout=30,
                    creationflags=subprocess.CREATE_NO_WINDOW, env=dict(os.environ, MWM_UI_SMOKE='1'))
                self.assertEqual(result.returncode, 0, result.stderr)
                replies = [json.loads(line) for line in result.stdout.splitlines()]
                self.assertEqual(len(replies), len(requests))
                self.assertTrue(all('error' in reply for reply in replies[:2]))
                self.assertEqual([reply['id'] for reply in replies[2:]], identifiers)
                self.assertTrue(all('result' in reply for reply in replies[2:]))
                self.assertEqual(list(Path(folder).iterdir()), [])

    def test_invalid_requests_do_not_kill_the_next_request(self):
        invalid = ['[]', 'null', '42', '"snapshot"', '{',
                   '{"id":6,"method":"snapshot","params":null}']
        requests = invalid + [json.dumps(dict(id=7, method='snapshot'))]
        with tempfile.TemporaryDirectory() as folder:
            result = subprocess.run([sys.executable, '-B', str(ROOT/'tests/desktop_worker_fixture.py'), folder],
                input='\n'.join(requests)+'\n', capture_output=True, text=True, encoding='utf8', timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW, env=dict(os.environ, MWM_UI_SMOKE='1'))
            self.assertEqual(result.returncode, 0, result.stderr)
            replies = [json.loads(line) for line in result.stdout.splitlines()]
            self.assertEqual(len(replies), len(requests))
            self.assertTrue(all('error' in reply for reply in replies[:-1]))
            self.assertEqual(replies[-1]['id'], 7)
            self.assertEqual(replies[-1]['result']['runtime'], folder)
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_shipped_presets_compile_for_saved_and_xinput_controllers(self):
        desktop = worker.Desktop()
        saved = worker.read_json(ROOT/'data/controller-calibration.json')
        presets = {'baseline':'sword-original', 'starter':'sword-rebuild-1-supported',
                   'trial':'sword-rebuild-1', 'maria':'sword-maria', 'maria_dash':'sword-maria-dash'}
        for method, filename in presets.items():
            for calibration in (saved, desktop.xinput_calibration(2)):
                with self.subTest(preset=method, backend=calibration['device']['backend']):
                    preset = desktop.dispatch(method, dict(calibration=calibration))
                    expected = worker.trainer.remap_preset(
                        worker.read_json(ROOT/'data/presets'/(filename+'.json')), saved, calibration)
                    self.assertEqual(preset, expected)
                    self.assertEqual(desktop.preview(dict(preset=preset, calibration=calibration))['preset'], preset)
