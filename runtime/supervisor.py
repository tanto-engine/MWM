# Persistent supervisor for the maintained runtime. Never compiles a session DLL.
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from engine_config import atomic_json, read_json
from process_support import PlayLock, process_identity, worker_command, register_runtime, unregister_runtime

from project_paths import MOD_ROOT
HERE = Path(os.environ.get('NIOH_RUNTIME_HOME', MOD_ROOT/'runtime'))
CODE = Path(os.environ.get('TANTO_RUNTIME_CODE', Path(__file__).resolve().parent))


def sleep_until(seconds, stop):
    # Stop interrupts retry backoff without waiting for its full duration.
    end = time.monotonic() + seconds
    while time.monotonic() < end and not stop.exists():
        time.sleep(min(.2, max(0, end-time.monotonic())))


def session_binary(snapshot, session, tag):
    # Retained modules may still be loaded: a tag can only reuse identical bytes.
    if len(tag) != 16 or any(c not in '0123456789abcdef' for c in tag):
        raise ValueError('Invalid runtime configuration tag')
    destination = session / ('boss_repeat_' + tag + '.dll')
    session.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        shutil.copy2(snapshot, destination)
    elif hashlib.sha256(destination.read_bytes()).digest() != hashlib.sha256(snapshot.read_bytes()).digest():
        raise ValueError('Existing runtime tag belongs to a different DLL build; refusing to replace a loaded module')
    return destination


def supervise(args):
    # Reacquire a player only after the preceding worker establishes safe cleanup.
    stop = HERE / 'stop.flag'
    session = HERE / 'sessions' / (time.strftime('%Y%m%d-%H%M%S-') + str(os.getpid()))
    session.mkdir(parents=True, exist_ok=True)
    attempt = 0
    last_message = None
    def status(state, **extra):
        # Publish transitions; process identity establishes liveness, not mtime.
        nonlocal last_message
        value = dict(state=state, **extra)
        if value == last_message:
            return
        atomic_json(HERE / 'play-status.json', dict(value, updated_at=time.time(), publisher_pid=os.getpid()))
        print(value, flush=True)
        last_message = value
    source = args.dll or HERE / 'native/build/nioh_skill_runtime.dll'
    if not source.is_file():
        status('runtime_missing', detail='Build the runtime with runtime/native/Build.ps1.')
        return 1
    # Keep a completed build for this entire play session, including reattachment.
    snapshot = session / 'runtime.dll'
    shutil.copy2(source, snapshot)
    env = dict(os.environ, NIOH_RUNTIME_BUILD_DLL=str(snapshot))
    atomic_json(HERE / 'play-process.json', dict(process_identity(), session=str(session)))
    status('preparing', detail='Loading owned move resources and resolving the player.')
    while not stop.exists():
        prepared = subprocess.run(worker_command(CODE/'prepare_session.py', '--outdir', HERE),
                                  capture_output=True, text=True, cwd=HERE,
                                  creationflags=subprocess.CREATE_NO_WINDOW, env=env)
        if prepared.returncode:
            detail = prepared.stderr.strip() or prepared.stdout.strip()
            try:
                failure = json.loads(detail)
            except ValueError:
                failure = {}
            if failure.get('retryable') is False:
                status('preparation_failed', detail=failure['message'][-1200:])
                return 1
            status('waiting_for_resources', detail=failure.get('message', detail)[-1200:],
                   limitation='Waiting for a supported player; source assets load independently.')
            sleep_until(4, stop)
            continue
        boss = read_json(HERE/'boss-session.json')
        if not boss:
            status('preparation_failed', detail='No valid session configuration was produced')
            return 1
        tag = boss['config_tag']
        dll = session_binary(snapshot, HERE/'sessions/runtime', tag)
        if stop.exists():
            break
        attempt += 1
        trace = session / f'trace-{attempt}'
        status('starting', pid=boss['session']['pid'], trace=str(trace))
        with (session/f'run-{attempt}.stdout.txt').open('w') as out, (session/f'run-{attempt}.stderr.txt').open('w') as err:
            child = subprocess.Popen(worker_command(CODE/'run_dispatch.py',
                '--profile', HERE/'session-profile.json', '--seconds', '0',
                '--dll', dll, '--outdir', trace, '--stop-file', stop), stdout=out, stderr=err,
                creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                while child.poll() is None:
                    if (trace/'ready.json').exists():
                        live = read_json(trace/'live.json', {})
                        status(live.get('state', 'enabled'), pid=boss['session']['pid'], trace=str(trace),
                               binding=read_json(HERE/'controller-binding.json', {}).get('name', 'Sword preset'))
                    time.sleep(.25)
            except BaseException:
                # The worker owns native restoration. Keep this supervisor and
                # its lock alive until that cleanup finishes; never kill it.
                stop.touch()
                child.wait()
                raise
        result = read_json(trace/'status.json', {})
        no_mutation = result.get('start_attempted') is False or (result.get('start_report') or {}).get('mutation_started') is False
        # Export success cannot override observed failure to restore the player.
        if result.get('post_stop_slots_restored') is False or not result.get('stop_completed') and not no_mutation:
            status('cleanup_needs_attention', trace=str(trace), errors=result.get('errors', []))
            return 1
        if stop.exists():
            break
        if not result.get('start_completed') and not no_mutation:
            status('start_failed', trace=str(trace), errors=result.get('errors', []))
            return 1
        status('refreshing_encounter', errors=result.get('errors', []))
        sleep_until(2, stop)
    status('stopped')
    return 0


def main(argv=None):
    # Keep the singleton held through native cleanup and registry removal.
    parser = argparse.ArgumentParser(description='Keep configured moves active across Nioh sessions.')
    parser.add_argument('--dll', type=Path, help='Prebuilt runtime DLL')
    args = parser.parse_args(argv)
    try:
        lock = PlayLock()
    except RuntimeError as error:
        print(str(error), flush=True)
        return 0
    registration = None
    try:
        from project_paths import DATA
        registration = register_runtime(HERE, DATA/'moves.json')
        return supervise(args)
    finally:
        try:
            if registration:
                unregister_runtime(registration)
        finally:
            lock.close()


if __name__ == '__main__':
    raise SystemExit(main())
