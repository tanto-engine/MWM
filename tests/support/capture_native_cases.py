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
        # Run the capture coordinator with controlled export and trace outcomes.
        # Patch stage execution and argv while retaining real status-file generation.
        # Cleanup behavior must depend on mutation evidence rather than exception text.
        calls = []
        def fake_run(command, outdir, name):
            # Replay the configured outcome for one native capture stage.
            # Log the stage and either raise its failure or return its export report.
            # Tests can verify Stop ordering without launching an injector or game process.
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
        # Describe a failure before or after remote mutation could have started.
        # Construct the same structured CommandFailure consumed by capture cleanup.
        # Only proven preflight failures may skip a defensive Stop attempt.
        report = dict(status='error', stage='preflight' if not mutation else 'export',
                      api='OpenProcess(query)' if not mutation else 'WaitForSingleObject(remote_thread)',
                      mutation_started=mutation, export_completed=False)
        return capture.CommandFailure('start', subprocess.CompletedProcess([], 1, '', json.dumps(report)))

    def test_preflight_failure_does_not_attempt_stop(self):
        # Avoid Stop when preflight proves that no native mutation started.
        # Return structured failure before any remote mutation could begin.
        # Calling Stop against an untouched process would be an unsupported side effect.
        calls, status = self.exercise(dict(start=self.failure(False)), 1)
        self.assertEqual(calls, ['start'])
        self.assertFalse(status['start_completed'])
        self.assertFalse(status['stop_attempted'])
        self.assertIsNone(status['stopped'])
        self.assertEqual(status['stop_skipped_reason'], 'loader_confirmed_no_remote_mutation')

    def test_unknown_export_completion_attempts_stop(self):
        # Attempt Stop when a remote export may still have executed.
        # Report that remote execution started but its completion is unknown.
        # Cleanup must attempt Stop because the observer may already be active.
        calls, status = self.exercise(dict(start=self.failure(True), stop=SUCCESS), 1)
        self.assertEqual(calls, ['start', 'stop'])
        self.assertFalse(status['start_completed'])
        self.assertTrue(status['stop_attempted'] and status['stop_completed'])

    def test_unstructured_failure_is_conservative(self):
        # Treat an unstructured loader failure as uncertain native state.
        # Raise a failure without trustworthy mutation-stage metadata.
        # The coordinator must not infer that injection never started.
        calls, status = self.exercise(dict(start=RuntimeError('no diagnostic output'), stop=SUCCESS), 1)
        self.assertEqual(calls, ['start', 'stop'])
        self.assertTrue(status['stop_attempted'])

    def test_trace_failure_still_stops_completed_start(self):
        # Stop an enabled runtime even when trace collection fails.
        # Complete observer startup and then fail trace collection.
        # A downstream recording error must not leave the native observer enabled.
        calls, status = self.exercise(dict(start=SUCCESS, trace=RuntimeError('reader failed'), stop=SUCCESS), 1)
        self.assertEqual(calls, ['start', 'trace', 'stop'])
        self.assertTrue(status['start_completed'] and status['stop_completed'])
        self.assertFalse(status['trace_complete'])

    def test_success_reports_each_completed_stage(self):
        # Report each completed capture stage without losing its cleanup obligations.
        # Replay successful Start, trace and Stop export reports.
        # The final status must describe verified stage completion rather than mere command launch.
        calls, status = self.exercise(dict(start=SUCCESS, trace='{}', stop=SUCCESS), 0)
        self.assertEqual(calls, ['start', 'trace', 'stop'])
        self.assertTrue(all(status[k] for k in ['start_completed', 'stop_attempted', 'stop_completed', 'trace_complete', 'stopped']))
