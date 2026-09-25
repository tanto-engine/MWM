"""Keep the mod available, refreshing session addresses after a clean stop."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from prepare_session import native_code_hash

HERE = Path(__file__).resolve().parent


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--minhook', type=Path, default=HERE.parent.parent / 'third_party' / 'minhook',
                        help='MinHook source directory (default: vendored third_party/minhook)')
    args = parser.parse_args(argv)
    stop = HERE / 'stop.flag'
    session = HERE / 'sessions' / time.strftime('%Y%m%d-%H%M%S')
    session.mkdir(parents=True, exist_ok=True)
    attempt = 0
    last_message = None
    started_code = native_code_hash()
    env = os.environ.copy()
    gcc = Path(os.environ['USERPROFILE']) / 'AppData/Local/Scoop/apps/gcc/current/bin'
    if gcc.exists():
        env['PATH'] = str(gcc) + os.pathsep + env.get('PATH', '')
    def status(state, **extra):
        nonlocal last_message
        value = dict(state=state, **extra)
        (HERE / 'play-status.json').write_text(json.dumps(value, indent=2))
        message = json.dumps(value)
        if message != last_message:
            print(message, flush=True)
            last_message = message
    while not stop.exists():
        # Reattachment may refresh addresses, but must not silently pick up
        # unfinished source edits made while this play session is running.
        if native_code_hash() != started_code:
            status('source_changed', detail='Restart the launcher after the edited build is ready.')
            time.sleep(2)
            continue
        prepared = subprocess.run([sys.executable, '-B', str(HERE/'prepare_session.py'), '--outdir', str(HERE)],
                                  capture_output=True, text=True, cwd=HERE)
        if prepared.returncode:
            status('waiting_for_okatsu', detail=prepared.stderr.strip()[-1200:])
            time.sleep(4)
            continue
        boss = json.loads((HERE/'boss-session.json').read_text())
        tag = boss['config_tag']
        dll = HERE / 'native/build' / f'boss_repeat_{tag}.dll'
        if not dll.exists():
            built = subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',
                                     str(HERE/'native/build-repeat.ps1'),'-OutputName',f'boss_repeat_{tag}',
                                     '-MinHook',str(args.minhook.resolve())],
                                    capture_output=True,text=True,env=env)
            (session/f'build-{tag}.txt').write_text(built.stdout+'\n'+built.stderr)
            if built.returncode:
                status('build_failed', detail=built.stderr[-1200:])
                return 1
        if stop.exists():
            break
        if native_code_hash() != started_code:
            continue
        attempt += 1
        trace = session/f'trace-{attempt}'
        status('starting', pid=boss['session']['pid'], tag=tag, trace=str(trace))
        with (session/f'run-{attempt}.stdout.txt').open('w') as out, (session/f'run-{attempt}.stderr.txt').open('w') as err:
            child = subprocess.Popen([sys.executable,'-B',str(HERE/'run_dispatch.py'),
                '--profile',str(HERE/'session-profile.json'),'--boss','--repeat','--seconds','0',
                '--dll',str(dll),'--outdir',str(trace),'--stop-file',str(stop)],stdout=out,stderr=err)
            while child.poll() is None:
                if (trace/'ready.json').exists():
                    status('enabled', pid=boss['session']['pid'], tag=tag, trace=str(trace),
                           binding='LB + Circle: tap Charged Rush / hold Leaping Slash')
                time.sleep(.25)
        result = json.loads((trace/'status.json').read_text()) if (trace/'status.json').exists() else {}
        no_mutation = result.get('start_report', {}).get('mutation_started') is False if result.get('start_report') else False
        if not result.get('stop_completed') and not no_mutation:
            status('cleanup_needs_attention', trace=str(trace), errors=result.get('errors',[]))
            return 1
        if stop.exists():
            break
        # A native start error is not an encounter reload. Do not inject again.
        if not result.get('start_completed'):
            status('start_failed', trace=str(trace), errors=result.get('errors',[]))
            return 1
        status('refreshing_encounter', errors=result.get('errors',[]))
        time.sleep(2)
    status('stopped')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
