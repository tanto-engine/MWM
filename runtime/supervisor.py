# Persistent supervisor for the maintained runtime. Never compiles a session DLL.
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import time
from engine_config import atomic_json, read_json
from process_support import PlayLock, process_identity, worker_command, register_runtime, unregister_runtime

HERE = Path(os.environ.get('NIOH_RUNTIME_HOME', Path(__file__).resolve().parent))
CODE = Path(__file__).resolve().parent


def sleep_until(seconds, stop):
    # Wait between attachment attempts while honoring a stop request.
    # Use short sleeps against a monotonic deadline and the stop file.
    # The supervisor remains responsive while gameplay is unavailable.
    end = time.monotonic() + seconds
    while time.monotonic() < end and not stop.exists():
        time.sleep(min(.2, max(0, end-time.monotonic())))


def session_binary(snapshot, session, tag):
    # Keep a stable module filename for each configuration generation.
    # Reuse identical bytes and reject a tag collision with another build.
    # Already-loaded native modules must never be overwritten.
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
    # Keep the selected moves active through valid gameplay generations.
    # Prepare fresh resources, run one worker and wait for native cleanup.
    # Retries resume automatically without compiling for the current mission.
    stop = HERE / 'stop.flag'
    session = HERE / 'sessions' / (time.strftime('%Y%m%d-%H%M%S-') + str(os.getpid()))
    session.mkdir(parents=True, exist_ok=True)
    attempt = 0
    last_message = None
    def status(state, **extra):
        # Publish the current supervisor state and failure context.
        # Atomically replace the status file and print only changed states.
        # The UI sees actionable transitions without repeated log noise.
        nonlocal last_message
        value = dict(state=state, **extra)
        atomic_json(HERE / 'play-status.json', dict(value, updated_at=time.time(), publisher_pid=os.getpid()))
        if value != last_message:
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
            status('waiting_for_resources', detail=prepared.stderr.strip()[-1200:] or prepared.stdout.strip()[-1200:],
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
        if not result.get('stop_completed') and not no_mutation:
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
    # Own the singleton and registry around the supervisor lifecycle.
    # Parse source options, acquire the lock and clean registration on exit.
    # A second launch reuses the running supervisor instead of competing.
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
        root = Path(__file__).resolve().parents[1]
        registration = register_runtime(HERE, os.environ.get('NIOH_CATALOGUE_PATH', root / 'outputs/Nioh1-Sword-Move-Observations.xlsx'))
        return supervise(args)
    finally:
        try:
            if registration:
                unregister_runtime(registration)
        finally:
            lock.close()


if __name__ == '__main__':
    raise SystemExit(main())
