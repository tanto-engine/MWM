"""Mock subprocess outcomes only: no process or DLL is started by these tests."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
path = ROOT / 'outputs/okatsu-prototype/capture_native.py'
spec = importlib.util.spec_from_file_location('capture_native', path)
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)
SUCCESS = json.dumps(dict(status='export_returned', result=0, mutation_started=True,
                          export_thread_started=True, export_completed=True))


class CaptureTests(unittest.TestCase):
    def exercise(self, outcomes, expected_exit):
        calls = []
        def fake_run(command, outdir, name):
            calls.append(name)
            result = outcomes[name]
            if isinstance(result, Exception):
                raise result
            return result
        with tempfile.TemporaryDirectory(dir=ROOT / 'work/native-tests') as temp:
            output = Path(temp) / 'capture'
            argv = ['capture_native.py', '--pid', '123', '--creation-filetime', '456',
                    '--dll', 'fake.dll', '--outdir', str(output)]
            with patch.object(sys, 'argv', argv), patch.object(capture, 'run', side_effect=fake_run), \
                 contextlib.redirect_stdout(io.StringIO()):
                if expected_exit:
                    with self.assertRaises(SystemExit) as error:
                        capture.main()
                    self.assertEqual(error.exception.code, expected_exit)
                else:
                    capture.main()
            status = json.loads((output / 'status.json').read_text())
        return calls, status

    def failure(self, mutation):
        report = dict(status='error', stage='preflight' if not mutation else 'export',
                      api='OpenProcess(query)' if not mutation else 'WaitForSingleObject(remote_thread)',
                      mutation_started=mutation, export_completed=False)
        return capture.CommandFailure('start', subprocess.CompletedProcess([], 1, '', json.dumps(report)))

    def test_preflight_failure_does_not_attempt_stop(self):
        calls, status = self.exercise(dict(start=self.failure(False)), 1)
        self.assertEqual(calls, ['start'])
        self.assertFalse(status['start_completed'])
        self.assertFalse(status['stop_attempted'])
        self.assertIsNone(status['stopped'])
        self.assertEqual(status['stop_skipped_reason'], 'loader_confirmed_no_remote_mutation')

    def test_unknown_export_completion_attempts_stop(self):
        calls, status = self.exercise(dict(start=self.failure(True), stop=SUCCESS), 1)
        self.assertEqual(calls, ['start', 'stop'])
        self.assertFalse(status['start_completed'])
        self.assertTrue(status['stop_attempted'] and status['stop_completed'])

    def test_unstructured_failure_is_conservative(self):
        calls, status = self.exercise(dict(start=RuntimeError('no diagnostic output'), stop=SUCCESS), 1)
        self.assertEqual(calls, ['start', 'stop'])
        self.assertTrue(status['stop_attempted'])

    def test_trace_failure_still_stops_completed_start(self):
        calls, status = self.exercise(dict(start=SUCCESS, trace=RuntimeError('reader failed'), stop=SUCCESS), 1)
        self.assertEqual(calls, ['start', 'trace', 'stop'])
        self.assertTrue(status['start_completed'] and status['stop_completed'])
        self.assertFalse(status['trace_complete'])

    def test_success_reports_each_completed_stage(self):
        calls, status = self.exercise(dict(start=SUCCESS, trace='{}', stop=SUCCESS), 0)
        self.assertEqual(calls, ['start', 'trace', 'stop'])
        self.assertTrue(all(status[k] for k in ['start_completed', 'stop_attempted', 'stop_completed', 'trace_complete', 'stopped']))


if __name__ == '__main__':
    unittest.main()
