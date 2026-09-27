"""Line-delimited desktop requests; configuration uses the existing Engine validators."""
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import sys

import trainer
from engine_config import DEFAULT_PRESET, atomic_json, binding_for_preset, move_capabilities, read_json, validate_preset
from game_controller import BindingCapture, GameController, binding_buttons
from controller_reader import ControllerReader
from process_support import active_runtime, process_matches
from trace_reader import Trace
from prepare_session import configured_imports, configured_replacements, compiled_move_settings, compiled_skill_bindings
from binding_groups import describe_groups, export_group, import_group


class Desktop:
    def __init__(self):
        # Keep one temporary controller listener for this window's binding flow.
        # The worker reuses Engine configuration and lifecycle code without constructing Tk widgets.
        # Opening the UI does not attach to the game or write a default preset.
        self.capture = self.reader = self.trace = None
        self.child = None
        self.capabilities = move_capabilities()

    def location(self):
        # Aim settings at the registered Engine when it is already running.
        # An expected path on writes prevents a stale window from editing another active runtime.
        # Otherwise retain the existing Sword settings namespace for backwards compatibility.
        if os.environ.get('MWM_UI_SMOKE') == '1':
            return trainer.RUNTIME
        registration = active_runtime()
        runtime = Path(registration['runtime_path']) if registration else trainer.RUNTIME
        return runtime

    def snapshot(self):
        # Read the current reviewed choices and saved settings for display.
        # Missing local settings display shipped defaults without creating files.
        # A surviving status file is only live when its process identity still matches.
        runtime = self.location()
        source_calibration = read_json(trainer.ROOT/'data/controller-calibration.json')
        calibration = read_json(runtime/'controller-calibration.json', source_calibration)
        warning = ''
        try:
            saved = read_json(runtime/'controller-binding.json')
            preset = (trainer.remap_preset(DEFAULT_PRESET, source_calibration, calibration) if saved is None else validate_preset(saved))
        except (ValueError, KeyError, TypeError) as error:
            preset = trainer.remap_preset(DEFAULT_PRESET, source_calibration, calibration)
            warning = 'Saved moveset could not be loaded. Showing a baseline draft; the saved file is unchanged. ' + str(error)
        alive = process_matches(read_json(runtime/'play-process.json'))
        state = read_json(runtime/'play-status.json', {}) if alive else {}
        return dict(runtime=str(runtime), preset=preset, calibration=calibration,
                    buttons=binding_buttons(calibration['device'], calibration.get('button_map')),
                    capabilities=self.capabilities, running=alive,
                    binding_groups=describe_groups(), load_warning=warning,
                    status=state.get('state', 'disabled'), detail=state.get('detail', ''),
                    nioh_exe=read_json(runtime/'trainer-settings.json', {}).get('nioh_exe', ''))

    def validate(self, params):
        # Validate the entire pending preset, including source/stance conflicts and bounded speeds.
        # Button masks must belong to the selected controller's reviewed mapping.
        # Returning the normalized value does not apply settings or enable gameplay.
        preset = validate_preset(params['preset'])
        calibration = params['calibration']
        buttons = binding_buttons(calibration['device'], calibration.get('button_map'))
        if any(preset[key] not in buttons.values() for key in ('modifier_mask', 'trigger_mask')):
            raise ValueError('Choose buttons supported by the selected controller mapping')
        slot = calibration.get('controller_slot')
        if slot is not None and (type(slot) is not int or slot not in (0, 1, 2, 3)):
            raise ValueError('Controller slot must be automatic or 1–4')
        binding_for_preset(calibration, preset)
        return preset

    def preview(self, params):
        # Compile pending choices without attaching to Nioh or writing settings.
        # Use the same graph expansion and inherited speeds as live preparation.
        # Report effective per-phase values so a child override is distinct from inheritance.
        preset = self.validate(params)
        baseline = configured_imports(preset)
        replacements = configured_replacements(preset, baseline)
        imports = baseline['moves'] + (replacements['moves'] if replacements else [])
        compiled_skill_bindings(preset, imports)
        settings = compiled_move_settings(preset, imports)
        used = {move['id'] for move in replacements['moves']} if replacements else set()
        used.update([preset['tap_move'], preset['hold_move'], *preset['frost_moon'].values()])
        used.update(binding['move'] for binding in preset['skill_bindings'])
        if preset['string_enabled']:
            used.update(move['id'] for move in baseline['moves'])
        return dict(preset=preset, used=sorted(identifier for identifier in used if identifier),
                    moves={move['id']: value for move, value in zip(imports, settings)})

    def apply(self, params):
        # Save a validated configuration only to the runtime this window originally displayed.
        # Engine readers receive complete JSON files through the maintained atomic writer.
        # Changing a controller requires a stopped Engine so two settings files cannot mix live layouts.
        runtime = self.location()
        if str(runtime) != params['runtime']:
            raise ValueError('Active Engine changed. Reload settings before applying.')
        preset = self.preview(params)['preset']
        previous = read_json(runtime/'controller-calibration.json', read_json(trainer.ROOT/'data/controller-calibration.json'))
        if previous != params['calibration'] and process_matches(read_json(runtime/'play-process.json')):
            raise ValueError('Disable the Engine before changing controller mapping or slot')
        self.cancel_capture()
        atomic_json(runtime/'controller-calibration.json', params['calibration'])
        atomic_json(runtime/'controller-binding.json', preset)
        atomic_json(runtime/'trainer-settings.json', dict(nioh_exe=params.get('nioh_exe', '')))
        return self.snapshot()

    def add_override(self, params):
        # Seed a reusable row in an unoccupied source/stance rather than duplicating the first row.
        # Try reviewed moves against real graph compilation, including stance ownership and slot limits.
        # Return a new draft only; a full table or incompatible setup leaves the caller unchanged.
        preset = self.validate(params)
        if len(preset['skill_bindings']) + sum(value is not None for value in preset['stance_holds'].values()) >= 8:
            raise ValueError('All eight override slots are occupied. Remove an override or held-heavy binding first.')
        for source in self.capabilities['native_sources']:
            for stance in self.capabilities['stances']:
                if any(row['source'] == source['id'] and row['stance'] in (stance, 'any') for row in preset['skill_bindings']):
                    continue
                for move in self.capabilities['moves']:
                    if not move['native']:
                        continue
                    candidate = deepcopy(preset)
                    candidate['skill_bindings'].append(dict(source=source['id'], stance=stance, move=move['id']))
                    try:
                        return self.preview(dict(params, preset=candidate))['preset']
                    except ValueError:
                        continue
        raise ValueError('No compatible override slot is available with these bindings.')

    def cancel_capture(self):
        # Cancel a pending press without changing either preset button.
        # Release the optional native observation mapping held by this listener.
        # Re-arming always requires a new neutral state before accepting input.
        self.capture = self.reader = None
        if self.trace:
            self.trace.close()
        self.trace = None

    def start_capture(self, calibration):
        # Listen for one supported controller input after the user releases all controls.
        # Use Engine's published observation when attached; otherwise poll supported OS controllers.
        # This reads input only and never enables Engine or changes game memory.
        self.cancel_capture()
        try:
            self.capture = BindingCapture(calibration)
            runtime = self.location()
            if process_matches(read_json(runtime/'play-process.json')):
                session = read_json(runtime/'boss-session.json')
                self.trace = Trace(session['session']['pid'], 'NiohBossRepeatTrace_v2', tag=session['config_tag'])
                self.reader = ControllerReader(backends=[GameController(self.trace, calibration)])
            else:
                self.reader = ControllerReader()
            return dict(status=self.capture.status)
        except Exception:
            self.cancel_capture()
            raise

    def poll_capture(self):
        # Consume only the temporary listener's newest observations.
        # Engine's capture state rejects held inputs, reconnects and unsupported combinations.
        # Completion returns a pending form value; Apply remains the persistence boundary.
        if not self.capture:
            return dict(status='Binding cancelled')
        for event in self.reader.poll():
            result = self.capture.process(event)
            if result:
                self.cancel_capture()
                return result
        return dict(status=self.capture.status)

    def dispatch(self, method, params):
        # Dispatch a fixed set of configuration operations instead of evaluating renderer code.
        # File paths reach this worker only through main-process open/save dialogs.
        # TODO(pack-registry): replace sword-only capability discovery after Engine exposes reviewed weapon manifests.
        if os.environ.get('MWM_UI_SMOKE') == '1' and method in ('enable', 'disable', 'capture_start', 'capture_poll'):
            raise ValueError('Game and controller operations are disabled during the packaged UI check')
        if method == 'snapshot':
            return self.snapshot()
        if method == 'validate':
            return self.validate(params)
        if method == 'preview':
            return self.preview(params)
        if method == 'add_override':
            return self.add_override(params)
        if method == 'apply':
            return self.apply(params)
        if method == 'baseline':
            return trainer.remap_preset(DEFAULT_PRESET, read_json(trainer.ROOT/'data/controller-calibration.json'), params['calibration'])
        if method == 'starter':
            return trainer.remap_preset(validate_preset(read_json(trainer.ROOT/'data/presets/sword-rebuild-1-supported.json')),
                                       read_json(trainer.ROOT/'data/controller-calibration.json'), params['calibration'])
        if method == 'trial':
            return trainer.remap_preset(validate_preset(read_json(trainer.ROOT/'data/presets/sword-rebuild-1.json')),
                                       read_json(trainer.ROOT/'data/controller-calibration.json'), params['calibration'])
        if method == 'controller':
            choice = params['choice']
            if choice not in ('saved', 'ds4', '1', '2', '3', '4'):
                raise ValueError('Choose a saved mapping, DS4 or XInput controller 1–4')
            calibration = (self.snapshot()['calibration'] if choice == 'saved' else
                           read_json(trainer.ROOT/'data/controller-calibration.json') if choice == 'ds4' else
                           dict(schema=1, device=dict(backend='xinput', slot=int(choice)-1), lb_mask=0x100,
                                lt=dict(axis='lt', neutral=0, full=255), controller_slot=int(choice)-1))
            return dict(calibration=calibration, preset=trainer.remap_preset(params['preset'], params['calibration'], calibration),
                        buttons=binding_buttons(calibration['device'], calibration.get('button_map')))
        if method == 'export':
            preset = self.preview(params)['preset']
            atomic_json(params['path'], dict(schema_version=1, kind='sword_moveset', preset=preset,
                        controller={key:params['calibration'][key] for key in ('device', 'button_map') if key in params['calibration']}))
            return True
        if method == 'binding_export':
            value = export_group(self.preview(params)['preset'], params['calibration'], params['group'])
            atomic_json(params['path'], value)
            return True
        if method == 'binding_import':
            candidate = import_group(read_json(params['path']), params['preset'], params['calibration'], params['group'])
            return self.preview(dict(params, preset=candidate))['preset']
        if method == 'import':
            return trainer.saved_moveset(read_json(params['path']), params['calibration'])
        if method == 'capture_start':
            return self.start_capture(params['calibration'])
        if method == 'capture_poll':
            return self.poll_capture()
        if method == 'capture_cancel':
            self.cancel_capture()
            return True
        if method == 'disable':
            trainer.disable_engine()
            return True
        if method == 'enable':
            self.apply(params)
            runtime = self.location()
            trainer.RUNTIME = runtime
            os.environ['NIOH_RUNTIME_HOME'] = str(runtime)
            if params.get('nioh_exe'):
                os.environ['NIOH_EXE'] = params['nioh_exe']
            else:
                os.environ.pop('NIOH_EXE', None)
            # An already-running Engine owns its loaded libraries; repeated Enable only reuses that owner.
            if not process_matches(read_json(runtime/'play-process.json')):
                native = runtime/'native/build'
                native.mkdir(parents=True, exist_ok=True)
                for source in (trainer.CODE/'native/build').glob('*.dll'):
                    if source.resolve() != (native/source.name).resolve():
                        shutil.copyfile(source, native/source.name)
            self.child = trainer.launch_engine()
            return True
        raise ValueError('Unsupported desktop operation')


def main():
    # Keep stdin/stdout as one-request/one-reply JSON lines for Electron's private pipe.
    # Recoverable request failures report an error without killing the next configuration operation.
    # Closing the UI closes only this worker, preserving Engine's established explicit Disable lifecycle.
    # Electron writes UTF-8 bytes even when Windows' local code page is different.
    # Keep names and exported notes unchanged on both sides of the private pipe.
    sys.stdin.reconfigure(encoding='utf-8')
    sys.stdout.reconfigure(encoding='utf-8')
    desktop = Desktop()
    try:
        for line in sys.stdin:
            request = {}
            try:
                request = json.loads(line)
                result = desktop.dispatch(request['method'], request.get('params', {}))
                reply = dict(id=request['id'], result=result)
            except (ValueError, KeyError, TypeError, OSError, RuntimeError) as error:
                reply = dict(id=request.get('id'), error=str(error))
            print(json.dumps(reply, allow_nan=False), flush=True)
    finally:
        desktop.cancel_capture()


if __name__ == '__main__':
    main()
