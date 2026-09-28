# Offline regression cases for worker reacquisition and recovery after actor/process replacement.
# Fixtures isolate game/process effects; these checks do not establish gameplay acceptance.
# Loaded by the existing Engine test entrypoints through Test-Offline.ps1; see CODE_GUIDE.md.
import argparse
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'runtime'))
import supervisor as play


class Recovery(unittest.TestCase):
    def test_native_resource_failure_stops_activation_without_retry(self):
        # A pending native load may still own callbacks even after its frame hook detaches.
        # Feed its explicit terminal error through the real supervisor control flow.
        # Do not launch gameplay or repeatedly stack new resource requests in that process.
        for message in ('Hideyori resource load stalled', 'Native resource load failed: ' + 'x'*1400):
            with self.subTest(length=len(message)), tempfile.TemporaryDirectory() as temporary:
                runtime = Path(temporary)
                dll = runtime/'prebuilt.dll'
                dll.write_bytes(b'owned fixture; never loaded')
                failure = types.SimpleNamespace(returncode=1, stdout='', stderr=json.dumps(
                    dict(status='error', message=message, retryable=False)))
                with patch.object(play, 'HERE', runtime), patch.object(play.subprocess, 'run', return_value=failure) as prepare, \
                     patch.object(play, 'sleep_until', side_effect=AssertionError('Unexpected retry')), \
                     patch.object(play, 'process_identity', return_value=dict(publisher_pid=12)), \
                     contextlib.redirect_stdout(io.StringIO()):
                    result = play.supervise(argparse.Namespace(dll=dll))
                self.assertEqual(result, 1)
                self.assertEqual(prepare.call_count, 1)
                status = json.loads((runtime/'play-status.json').read_text())
                self.assertEqual((status['state'], status['detail']), ('preparation_failed', message[-1200:]))

    def exercise(self, result):
        # Run the play supervisor with a prebuilt dummy DLL and controlled worker report.
        # Mock preparation and children while retaining status and retry decisions.
        # Recovery must distinguish proven pre-mutation exits from unknown worker failure.
        with tempfile.TemporaryDirectory() as temporary:
            runtime = Path(temporary)
            dll = runtime/'prebuilt.dll'
            dll.write_bytes(b'owned fixture; never loaded')
            attempts = []
            def prepare(command, **kwargs):
                # Write a fresh session fixture for each simulated preparation attempt.
                # Create Stop after the second attempt to bound automatic reacquisition.
                # Tests can detect retries without compiling or deploying a runtime.
                attempts.append(command)
                (runtime/'boss-session.json').write_text(json.dumps(dict(config_tag='0123456789abcdef',session=dict(pid=123))))
                if len(attempts) == 2:
                    (runtime/'stop.flag').touch()
                return types.SimpleNamespace(returncode=0, stdout='', stderr='')
            def child(command, **kwargs):
                # Create a worker trace folder and optionally publish its failure evidence.
                # Return an already-exited child rather than spawning gameplay code.
                # The supervisor must decide recovery from the report, not assume all exits are safe.
                trace = Path(command[command.index('--outdir')+1])
                trace.mkdir()
                if result is not None:
                    (trace/'status.json').write_text(json.dumps(result))
                return types.SimpleNamespace(poll=lambda: (
                    # Report that the fake dispatcher child has already exited.
                    # Return a nonzero exit code on every poll.
                    # Supervisor retry policy must inspect its retained stage evidence after failure.
                    1
                ))
            with patch.object(play, 'HERE', runtime), patch.object(play.subprocess, 'run', side_effect=prepare), \
                 patch.object(play.subprocess, 'Popen', side_effect=child), patch.object(play, 'sleep_until'), \
                 patch.object(play, 'process_identity', return_value=dict(publisher_pid=12,publisher_start_filetime='34')), \
                 contextlib.redirect_stdout(io.StringIO()):
                exitcode = play.supervise(argparse.Namespace(dll=dll))
            status = json.loads((runtime/'play-status.json').read_text())
            return exitcode, len(attempts), status

    def test_actor_change_before_loader_retries_automatically(self):
        # Retry session preparation when the player changes before native startup.
        # Return a worker report proving actor change happened before remote mutation.
        # The supervisor may prepare fresh identities and retry without requiring manual restart.
        code, attempts, status = self.exercise(dict(start_attempted=False, start_completed=False,
            stop_completed=False, errors=['Actor replaced before attachment']))
        self.assertEqual((code, attempts, status['state']), (0, 2, 'stopped'))

    def test_unknown_worker_failure_never_assumes_no_mutation(self):
        # Keep an unknown worker failure from implying that no native mutation occurred.
        # Exit the worker without a trustworthy stage report.
        # Automatic retry must not infer safe nonmutation from missing evidence.
        code, attempts, status = self.exercise(None)
        self.assertEqual((code, attempts, status['state']), (1, 1, 'cleanup_needs_attention'))

    def test_retired_game_process_allows_reacquisition(self):
        # Reacquire only after the previous game process is positively retired.
        # Report that the prior game process has retired.
        # Fresh process discovery is safe because its old remote state no longer exists.
        code, attempts, status = self.exercise(dict(start_attempted=True, start_completed=True,
            stop_completed=True, process_retired=True, errors=['Game exited']))
        self.assertEqual((code, attempts, status['state']), (0, 2, 'stopped'))
