# Preset migration and headless lifecycle helpers shared by the Electron worker.
import argparse
from copy import deepcopy
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(os.environ.get('TANTO_MOD_ROOT', Path(__file__).resolve().parents[1]))
RUNTIME = Path(os.environ.get('NIOH_RUNTIME_HOME', ROOT/'runtime'))
CODE = Path(os.environ.get('TANTO_ENGINE_ROOT', ROOT.parent))/'runtime' if not (ROOT/'runtime/engine_config.py').is_file() else ROOT/'runtime'
os.environ['TANTO_MOD_ROOT'] = str(ROOT)
os.environ['NIOH_RUNTIME_HOME'] = str(RUNTIME)
sys.path.insert(0, str(CODE))

from engine_config import read_json, validate_preset
from game_controller import binding_buttons, game_button_mask
from process_support import active_runtime, process_matches, worker_command


def remap_preset(preset, source, target, top_level=True, custom_inputs=True):
    """Preserve logical buttons; group imports remap only their own mask namespace."""
    buttons=binding_buttons(target['device'],target.get('button_map'))
    masks={game_button_mask(target['device'],mask,target.get('button_map')):mask for mask in buttons.values()}
    result=deepcopy(preset)
    def remap(mask):
        logical=game_button_mask(source['device'],mask,source.get('button_map'))
        if logical not in masks: raise ValueError('This controller mapping does not support a saved input')
        return masks[logical]
    if top_level:
        for key in ('modifier_mask','trigger_mask'): result[key]=remap(result[key])
    for row in result['skill_bindings'] if custom_inputs else ():
        if 'input' in row:
            for key in ('modifier_mask','trigger_mask','followup_mask'):
                if key in row['input']: row['input'][key]=remap(row['input'][key])
    return validate_preset(result)


def saved_moveset(value, calibration):
    # Bundles carry their mask namespace; legacy bare presets use the current map.
    if isinstance(value,dict) and value.get('kind')=='sword_moveset':
        if value.get('schema_version')!=1 or set(value)!={'schema_version','kind','preset','controller'}:
            raise ValueError('Unsupported saved moveset bundle')
        return remap_preset(validate_preset(value['preset']),value['controller'],calibration)
    return validate_preset(value)


def launch(script, arguments, folder):
    # Frozen children need their own extraction lifetime when the UI exits first.
    folder.mkdir(parents=True, exist_ok=True)
    with (folder/'stdout.txt').open('w') as out, (folder/'stderr.txt').open('w') as err:
        return subprocess.Popen(worker_command(script, *arguments), stdout=out, stderr=err,
                                cwd=RUNTIME, creationflags=subprocess.CREATE_NO_WINDOW,
                                env=dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT='1') if getattr(sys,'frozen',False) else None)


def launch_engine():
    # Reopening the editor must not clear an existing supervisor's Stop request.
    if active_runtime() is not None:
        return None
    if process_matches(read_json(RUNTIME/'play-process.json')):
        return None
    native = RUNTIME/'native/build'
    native.mkdir(parents=True, exist_ok=True)
    for source in (CODE/'native/build').glob('*.dll'):
        if source.resolve() != (native/source.name).resolve():
            shutil.copyfile(source, native/source.name)
    if not (RUNTIME/'native/build/nioh_skill_runtime.dll').is_file():
        raise ValueError('Runtime is missing. Run runtime/native/Build.ps1 first.')
    (RUNTIME/'stop.flag').unlink(missing_ok=True)
    return launch(CODE/'supervisor.py', [], RUNTIME/'sessions'/('launcher-'+str(time.time_ns())))


def disable_engine():
    # Target the registered owner; its native recovery performs detachment.
    registration = active_runtime()
    runtime = Path(registration['runtime_path']) if registration else RUNTIME
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime/'stop.flag').write_text('stop\n')


def main(argv=None):
    # Headless Disable must not construct UI or stage a new runtime.
    parser = argparse.ArgumentParser(description='Control the Nioh sword runtime')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--enable', action='store_true', help='Enable without opening the UI')
    mode.add_argument('--disable', action='store_true', help='Cooperatively disable without opening the UI')
    args = parser.parse_args(argv)
    RUNTIME.mkdir(parents=True, exist_ok=True)
    if args.disable:
        disable_engine()
        return 0
    for source,target in [('controller-calibration.json','controller-calibration.json'),('preset.json','controller-binding.json')]:
        if not (RUNTIME/target).exists(): shutil.copyfile(ROOT/'data'/source,RUNTIME/target)
    if args.enable:
        settings = read_json(RUNTIME/'trainer-settings.json', {})
        if settings.get('nioh_exe'): os.environ['NIOH_EXE'] = settings['nioh_exe']
        launch_engine()
        return 0
    return subprocess.run(['pwsh.exe', '-NoProfile', '-File', str(ROOT/'Trainer.ps1'),
                           '-PythonRuntime', sys.executable], check=False).returncode



if __name__ == '__main__':
    raise SystemExit(main())
