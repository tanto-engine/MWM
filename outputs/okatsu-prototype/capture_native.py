# Bounded passive capture; stop after possible mutation, report preflight failures.
import argparse
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent


def loader_report(stdout, stderr=''):
    # Extract a loader result from either worker output stream.
    # Accept only recognized loader outcomes from valid JSON objects.
    # Keep mutation provenance available when deciding whether to stop a hook.
    for text in (stderr, stdout):
        try:
            value = json.loads(text)
        except (ValueError, TypeError):
            continue
        if isinstance(value, dict) and value.get('status') in ('error', 'export_returned'):
            return value
    return None


class CommandFailure(RuntimeError):
    def __init__(self, name, result):
        # Retain the failing worker name and its loader report.
        # Include stdout and stderr in the exception message.
        # Capture cleanup needs to distinguish failed start from later failures.
        super().__init__(f'{name} failed ({result.returncode}): {result.stderr.strip()} {result.stdout.strip()}')
        self.name = name
        self.report = loader_report(result.stdout, result.stderr)


def run(command, outdir, name):
    # Run one hidden capture worker and persist both output streams.
    # Raise with the worker identity when its exit code is nonzero.
    # Keep command failures reviewable after the parent exits.
    from process_support import worker_command
    result = subprocess.run(worker_command(command[0], *command[1:]),
                            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    (outdir / (name+'.stdout.txt')).write_text(result.stdout, encoding='utf8')
    (outdir / (name+'.stderr.txt')).write_text(result.stderr, encoding='utf8')
    if result.returncode:
        raise CommandFailure(name, result)
    return result.stdout


def main():
    # Bound a passive native trace by process identity and duration.
    # Attempt hook cleanup whenever start may have mutated the process.
    # Persist cleanup failures instead of claiming a clean capture.
    parser = argparse.ArgumentParser(description='Record a bounded native action trace.')
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--creation-filetime', required=True)
    parser.add_argument('--dll', type=Path, required=True)
    parser.add_argument('--seconds', type=float, default=5)
    parser.add_argument('--outdir', type=Path, required=True)
    parser.add_argument('--harness', action='store_true')
    parser.add_argument('--player', type=lambda x: (
        # Parse an explicit CLI address or action key.
        # Accept decimal and prefixed hexadecimal through Python integer parsing.
        # Reject malformed values before the command can attach to a process.
        int(x, 0)))
    parser.add_argument('--owner', type=lambda x: (
        # Parse an explicit CLI address or action key.
        # Accept decimal and prefixed hexadecimal through Python integer parsing.
        # Reject malformed values before the command can attach to a process.
        int(x, 0)))
    parser.add_argument('--calibration', type=Path)
    args = parser.parse_args()
    if not 0 < args.seconds <= 60:
        parser.error('Duration must be 0..60 seconds')
    if any(v is not None for v in (args.player, args.owner, args.calibration)) and not all(
            v is not None for v in (args.player, args.owner, args.calibration)):
        parser.error('Input capture requires --player, --owner and --calibration together')
    args.outdir.mkdir(parents=True, exist_ok=False)
    base = [HERE / 'native_loader.py', '--pid', args.pid, '--creation-filetime', args.creation_filetime,
            '--dll', args.dll.resolve()]
    if args.harness:
        base.append('--harness')
    status = dict(pid=args.pid, creation_filetime=args.creation_filetime, mode='passive_observer',
                  start_attempted=False, start_completed=False, start_report=None,
                  stop_attempted=False, stop_completed=False, stop_report=None,
                  stopped=None, trace_complete=False, errors=[])
    try:
        status['start_attempted'] = True
        output = run(base, args.outdir, 'start')
        status['start_report'] = loader_report(output)
        status['start_completed'] = True
        print('Passive hook started.', flush=True)
        if args.player is None:
            reader = [HERE / 'trace_reader.py', '--pid', args.pid, '--seconds', args.seconds,
                      '--out', args.outdir / 'native-events.jsonl']
        else:
            reader = [HERE / 'trace_inputs.py', '--pid', args.pid, '--seconds', args.seconds,
                      '--creation-filetime', args.creation_filetime,
                      '--player', hex(args.player), '--owner', hex(args.owner),
                      '--calibration', args.calibration.resolve(),
                      '--out', args.outdir / 'input-native-events.jsonl']
        run(reader, args.outdir, 'trace')
        status['trace_complete'] = True
    except Exception as error:
        if isinstance(error, CommandFailure) and error.name == 'start':
            status['start_report'] = error.report
        status['errors'].append(str(error))
    finally:
        # Only a loader-confirmed pre-mutation failure can skip Stop. Otherwise
        # cleanup runs even after an unexpected worker error, and its own error
        # is retained alongside the original failure in status.json.
        report = status['start_report']
        no_mutation = (report is not None and report.get('status') == 'error'
                       and report.get('mutation_started') is False)
        if no_mutation:
            status['stop_skipped_reason'] = 'loader_confirmed_no_remote_mutation'
        else:
            status['stop_attempted'] = True
            try:
                output = run([*base, '--export', 'NiohResearchStop'], args.outdir, 'stop')
                status['stop_report'] = loader_report(output)
                status['stop_completed'] = status['stopped'] = True
            except Exception as error:
                if isinstance(error, CommandFailure):
                    status['stop_report'] = error.report
                status['stopped'] = False
                status['errors'].append('Stop attempt: '+str(error))
        (args.outdir / 'status.json').write_text(json.dumps(status, indent=2)+'\n', encoding='utf8')
    print(json.dumps(status, indent=2), flush=True)
    if status['errors']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
