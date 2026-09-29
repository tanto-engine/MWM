"""Line-delimited desktop requests; configuration uses the existing Engine validators."""
from copy import deepcopy
import ctypes as C
import json
import os
from pathlib import Path
import sys
import time
from uuid import uuid4

import trainer
from engine_config import DEFAULT_PRESET, atomic_json, binding_for_preset, move_capabilities, read_json, validate_preset
from game_controller import BindingCapture, binding_buttons, game_binding, game_button_mask
from controller_reader import ControllerReader
from gestures import identity
from process_support import active_runtime, process_matches
from prepare_session import configured_imports, configured_replacements, compiled_move_settings, compiled_skill_bindings
from binding_groups import describe_groups, export_group, import_group


class BindingError(ValueError):
    """A rejected draft, distinct from worker, file or lifecycle failures."""


HOTKEY_MASK = 0x2000  # Direct WinMM DS4 button 14 (touchpad click); XInput has no touchpad bit.


class TouchpadDoubleTap:
    def __init__(self):
        self.first = None
        self.released = False
        self.cooldown = 0

    def feed(self, event):
        if event['kind'] == 'input_unavailable':
            self.first = None
            self.released = False
            return False
        if event['kind'] != 'input' or event.get('edge_basis') != 'previous_observation':
            return False
        now = event['observed_monotonic']
        if now < self.cooldown:
            return False
        if self.first is not None and now - self.first > .4:
            self.first = None
            self.released = False
        if event['buttons'] == 0 and event['released_mask'] == HOTKEY_MASK and self.first is not None:
            self.released = True
        elif event['buttons'] == HOTKEY_MASK and event['pressed_mask'] == HOTKEY_MASK:
            if self.first is not None and self.released:
                self.first = None
                self.released = False
                self.cooldown = now + 1
                return True
            self.first = now
            self.released = False
        elif event['buttons'] & ~HOTKEY_MASK:
            self.first = None
            self.released = False
        return False


def haptic_pulse(slot):
    """Give an opted-in XInput pad a short, gentle confirmation pulse."""
    if type(slot) is not int or not 0 <= slot < 4:
        return False
    class Vibration(C.Structure):
        _fields_ = [('left', C.c_ushort), ('right', C.c_ushort)]
    try:
        set_state = C.WinDLL('xinput1_4').XInputSetState
        set_state.argtypes = [C.c_uint32, C.POINTER(Vibration)]
        set_state.restype = C.c_uint32
        if set_state(slot, C.byref(Vibration(0, 4500))):
            return False
        try:
            time.sleep(.045)
        finally:
            set_state(slot, C.byref(Vibration()))
        return True
    except OSError:
        return False


class Desktop:
    def __init__(self):
        # Keep one temporary controller listener for this window's binding flow.
        # The worker reuses Engine configuration and lifecycle code without constructing Tk widgets.
        # Opening the UI does not attach to the game or write a default preset.
        self.capture = self.reader = None
        self.captures = {}
        self.child = None
        self.hotkey_reader = None
        self.hotkey_device = None
        self.hotkey_gesture = TouchpadDoubleTap()
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
        state = read_json(runtime/'play-status.json', {})
        if not alive and state.get('state') not in ('preparation_failed', 'cleanup_needs_attention', 'start_failed', 'runtime_missing'):
            state = {}
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
        game_binding(calibration, binding_for_preset(calibration, preset))
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
        # Saving requires a stopped Engine so edits cannot hot-reload native imports during combat.
        runtime = self.location()
        if str(runtime) != params['runtime']:
            raise ValueError('Active Engine changed. Reload settings before applying.')
        try:
            preset = self.preview(params)['preset']
        except ValueError as error:
            raise BindingError(str(error)) from error
        if process_matches(read_json(runtime/'play-process.json')):
            raise ValueError('Disable the mod before saving changes. Your edits remain in the editor.')
        self.cancel_capture()
        atomic_json(runtime/'controller-calibration.json', params['calibration'])
        atomic_json(runtime/'controller-binding.json', preset)
        atomic_json(runtime/'trainer-settings.json', dict(nioh_exe=params.get('nioh_exe', '')))
        return self.snapshot()

    def library(self, runtime):
        path = runtime/'moveset-library.json'
        if not path.exists():
            calibration = self.snapshot()['calibration']
            try:
                preset = self.preview(dict(preset=read_json(runtime/'controller-binding.json'), calibration=calibration))['preset']
            except (ValueError, KeyError, TypeError):
                pass
            else:
                identifier = uuid4().hex
                atomic_json(path, dict(schema_version=1, selected_id=identifier, presets=[dict(id=identifier,
                    preset=preset, controller={key:calibration[key] for key in ('device', 'button_map') if key in calibration})]))
        value = read_json(path, dict(schema_version=1, selected_id=None, presets=[]))
        if (not isinstance(value, dict) or set(value) != {'schema_version', 'selected_id', 'presets'}
                or type(value['schema_version']) is not int or value['schema_version'] != 1
                or not isinstance(value['presets'], list) or len(value['presets']) > 100):
            raise ValueError('Saved preset library is invalid')
        ids = set()
        for item in value['presets']:
            if (not isinstance(item, dict) or set(item) != {'id', 'preset', 'controller'}
                    or not isinstance(item['id'], str) or len(item['id']) != 32
                    or any(c not in '0123456789abcdef' for c in item['id']) or item['id'] in ids
                    or not isinstance(item['controller'], dict) or not isinstance(item['controller'].get('device'), dict)
                    or set(item['controller']) - {'device', 'button_map'}
                    or 'device' not in item['controller']):
                raise ValueError('Saved preset library is invalid')
            validate_preset(item['preset'])
            ids.add(item['id'])
        if value['selected_id'] is not None and value['selected_id'] not in ids:
            raise ValueError('Saved preset selection is invalid')
        return value

    def preset_list(self):
        runtime = self.location()
        value = self.library(runtime)
        calibration = self.snapshot()['calibration']
        selected = None
        try:
            saved = validate_preset(read_json(runtime/'controller-binding.json'))
            ordered = sorted(value['presets'], key=lambda item: item['id'] != value['selected_id'])
            for item in ordered:
                try:
                    candidate = trainer.saved_moveset(dict(schema_version=1, kind='sword_moveset',
                        preset=item['preset'], controller=item['controller']), calibration)
                except (ValueError, KeyError, TypeError):
                    continue
                if candidate == saved:
                    selected = item
                    break
        except (ValueError, KeyError, TypeError):
            pass
        return dict(presets=[dict(id=item['id'], name=item['preset']['name'],
                    native_routes=sum('input' not in row for row in item['preset']['skill_bindings']),
                    custom_routes=sum('input' in row for row in item['preset']['skill_bindings']),
                    speed_overrides=len(item['preset']['move_settings'])) for item in value['presets']],
                    selected_id=selected['id'] if selected else None,
                    hotkey=self.hotkey_capability(calibration))

    def preset_save(self, params):
        runtime = self.location()
        if params['runtime'] != str(runtime):
            raise ValueError('Active Engine changed. Reload settings before saving a preset.')
        preset = self.preview(params)['preset']
        value = self.library(runtime)
        controller = {key:params['calibration'][key] for key in ('device', 'button_map') if key in params['calibration']}
        matching = next((item['id'] for item in value['presets'] if item['preset'] == preset and item['controller'] == controller), None)
        identifier = params.get('id') or matching or uuid4().hex
        index = next((i for i, item in enumerate(value['presets']) if item['id'] == identifier), None)
        if index is None and (params.get('id') or len(value['presets']) >= 100):
            raise ValueError('Saved preset was not found or the library is full')
        item = dict(id=identifier, preset=preset, controller=controller)
        if index is None:
            value['presets'].append(item)
        else:
            value['presets'][index] = item
        if not process_matches(read_json(runtime/'play-process.json')) and read_json(runtime/'controller-binding.json') == preset:
            value['selected_id'] = identifier
        atomic_json(runtime/'moveset-library.json', value)
        return self.preset_list()

    def preset_load(self, params):
        runtime = self.location()
        if params['runtime'] != str(runtime):
            raise ValueError('Active Engine changed. Reload settings before loading a preset.')
        if params.get('dirty') and not params.get('discard_draft'):
            raise ValueError('Unsaved edits remain in the editor. Confirm replacing the draft first.')
        item = next((item for item in self.library(runtime)['presets'] if item['id'] == params['id']), None)
        if item is None:
            raise ValueError('Saved preset was not found')
        return self.preview(dict(params, preset=trainer.saved_moveset(dict(
            schema_version=1, kind='sword_moveset', preset=item['preset'], controller=item['controller']),
            params['calibration'])))['preset']

    def preset_delete(self, params):
        runtime = self.location()
        if params['runtime'] != str(runtime):
            raise ValueError('Active Engine changed. Reload settings before deleting a preset.')
        value = self.library(runtime)
        remaining = [item for item in value['presets'] if item['id'] != params['id']]
        if len(remaining) == len(value['presets']):
            raise ValueError('Saved preset was not found')
        value['presets'] = remaining
        if value['selected_id'] == params['id']:
            value['selected_id'] = None
        atomic_json(runtime/'moveset-library.json', value)
        return self.preset_list()

    @staticmethod
    def hotkey_capability(calibration):
        device = calibration.get('device', {})
        supported = (device.get('backend') == 'winmm'
                     and (device.get('manufacturer'), device.get('product')) in ((0x054c, 0x09cc), (0x054c, 0x05c4))
                     and device.get('num_buttons', 0) >= 14)
        return dict(supported=supported, label='Double-tap DS4 touchpad click' if supported else 'Use Switch in the app',
                    reason=('Requires an unmapped touchpad click; a simultaneous XInput button press cancels the switch.' if supported
                            else 'A distinct touchpad button is unavailable in this controller mapping (including XInput / Steam Input).'))

    def preset_hotkey_poll(self):
        runtime = self.location()
        if not process_matches(read_json(runtime/'play-process.json')):
            self.hotkey_gesture = TouchpadDoubleTap()
            return False
        if read_json(runtime/'play-status.json', {}).get('state') != 'enabled':
            self.hotkey_gesture = TouchpadDoubleTap()
            return False
        calibration = read_json(runtime/'controller-calibration.json', read_json(trainer.ROOT/'data/controller-calibration.json'))
        if not self.hotkey_capability(calibration)['supported']:
            return False
        device = calibration['device']
        if self.hotkey_device != device:
            self.hotkey_device = device
            self.hotkey_reader = ControllerReader()
            self.hotkey_gesture = TouchpadDoubleTap()
            self.hotkey_verified = False
            self.hotkey_xinput_press = float('-inf')
        events = self.hotkey_reader.poll()
        for event in events:
            if event['backend'] == 'xinput' and event['kind'] == 'input' and (event.get('pressed_mask') or event.get('logical_buttons', 0) & 0x0c00):
                self.hotkey_xinput_press = event['observed_monotonic']
        for event in events:
            if (event['backend'], event['slot']) != ('winmm', device['slot']):
                continue
            if event['kind'] == 'input_device':
                self.hotkey_verified = ((event.get('manufacturer'), event.get('product'))
                                        == (device['manufacturer'], device['product']) and event.get('num_buttons', 0) >= 14)
            if event['kind'] == 'input_unavailable':
                self.hotkey_verified = False
            if self.hotkey_verified and self.hotkey_gesture.feed(event):
                return event['observed_monotonic'] - self.hotkey_xinput_press > .6
        return False

    def preset_switch(self, params):
        runtime = self.location()
        if params['runtime'] != str(runtime):
            raise ValueError('Active Engine changed. Reload settings before switching presets.')
        value = self.library(runtime)
        target = next((item for item in value['presets'] if item['id'] == params['id']), None)
        if target is None:
            raise ValueError('Saved preset was not found')
        if self.preset_list()['selected_id'] == target['id']:
            return dict(presets=self.preset_list(), snapshot=self.snapshot())
        calibration = self.snapshot()['calibration']
        preset = self.preset_load(dict(runtime=str(runtime), id=target['id'], calibration=calibration))
        running = process_matches(read_json(runtime/'play-process.json')) or active_runtime() is not None
        if running:
            registration = active_runtime()
            if registration and Path(registration['runtime_path']) != runtime:
                raise RuntimeError('Active Engine changed. Reload settings before switching presets.')
            trainer.RUNTIME = runtime
            trainer.disable_engine()
            deadline = time.monotonic() + 30
            while process_matches(read_json(runtime/'play-process.json')) or active_runtime() is not None:
                if time.monotonic() >= deadline:
                    raise RuntimeError('Engine cleanup timed out; the mod remains disabled. Retry after it stops.')
                time.sleep(.1)
            status = read_json(runtime/'play-status.json', {})
            if status.get('state') != 'stopped':
                raise RuntimeError('Engine did not complete safe cleanup; the mod remains disabled.')
        self.apply(dict(runtime=str(runtime), preset=preset, calibration=calibration,
                        nioh_exe=read_json(runtime/'trainer-settings.json', {}).get('nioh_exe', '')))
        value['selected_id'] = target['id']
        atomic_json(runtime/'moveset-library.json', value)
        if running:
            os.environ['NIOH_RUNTIME_HOME'] = str(runtime)
            executable = read_json(runtime/'trainer-settings.json', {}).get('nioh_exe', '')
            if executable:
                os.environ['NIOH_EXE'] = executable
            else:
                os.environ.pop('NIOH_EXE', None)
            self.child = trainer.launch_engine()
            if self.child is None:
                raise RuntimeError('Engine did not restart; the mod remains disabled.')
        return dict(presets=self.preset_list(), snapshot=self.snapshot())

    def preset_cycle(self, params=None):
        runtime = self.location()
        if params and params.get('runtime') != str(runtime):
            raise ValueError('Active Engine changed. Reload settings before switching presets.')
        value = self.library(runtime)
        if len(value['presets']) < 2:
            raise ValueError('Save at least two presets to switch')
        current = self.preset_list()['selected_id']
        index = next((i for i, item in enumerate(value['presets']) if item['id'] == current), -1)
        return self.preset_switch(dict(runtime=str(runtime), id=value['presets'][(index + 1) % len(value['presets'])]['id']))

    def add_override(self, params):
        # Seed a reusable row in an unoccupied source/stance rather than duplicating the first row.
        # Try reviewed moves against real graph compilation, including stance ownership and slot limits.
        # Return a new draft only; a full table or incompatible setup leaves the caller unchanged.
        preset = self.validate(params)
        if params.get('mode') == 'custom':
            calibration=params['calibration']
            masks={game_button_mask(calibration['device'],mask,calibration.get('button_map')):mask
                   for mask in binding_buttons(calibration['device'],calibration.get('button_map')).values()}
            for gesture in ('tap','hold'):
                for logical in (0x2000,0x8000,0x400,0x4000):
                    if 0x100 not in masks or logical not in masks: continue
                    for stance in self.capabilities['stances']:
                        for move in self.capabilities['moves']:
                            if not move['chord']: continue
                            candidate=deepcopy(preset)
                            candidate['skill_bindings'].append(dict(source='tiger_sprint',stance=stance,move=move['id'],
                                input=dict(modifier_mask=masks[0x100],trigger_mask=masks[logical],gesture=gesture)))
                            try: return self.preview(dict(params,preset=candidate))['preset']
                            except ValueError: continue
            raise ValueError('No compatible custom input route is available with these bindings.')
        for source in self.capabilities['native_sources']:
            if params.get('source') and source['id'] != params['source']: continue
            for stance in self.capabilities['stances']:
                if params.get('stance') and stance != params['stance']: continue
                if any('input' not in row and row['source'] == source['id'] and row['stance'] in (stance, 'any') for row in preset['skill_bindings']):
                    continue
                for move in self.capabilities['moves']:
                    if not move['native'] or params.get('move') and move['id'] != params['move']:
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
        # Release the temporary OS controller listener.
        # Re-arming always requires a new neutral state before accepting input.
        self.capture = self.reader = None
        self.captures = {}

    @staticmethod
    def xinput_calibration(slot):
        return dict(schema=1, device=dict(backend='xinput', slot=slot), lb_mask=0x100,
                    lt=dict(axis='lt', neutral=0, full=255), controller_slot=slot)

    def detected_calibration(self, event):
        device = identity(event)
        if device == self.capture.device:
            return self.selected_calibration
        if event['backend'] == 'xinput':
            return self.xinput_calibration(event['slot'])
        if event['backend'] == 'winmm' and (device.get('manufacturer'), device.get('product')) in ((0x054c, 0x09cc), (0x054c, 0x05c4)):
            calibration = read_json(trainer.ROOT/'data/controller-calibration.json')
            return dict(calibration, device=device)
        return None

    def start_capture(self, calibration):
        # Listen to OS controllers whether Nioh is running or not. Detect the physical
        # source of the press instead of silently ignoring a controller different from
        # the saved mapping. Game traces can stop publishing while the game is paused.
        self.cancel_capture()
        try:
            self.capture = BindingCapture(calibration)
            self.selected_calibration = calibration
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
        events = sorted(self.reader.poll(), key=lambda event: event['backend'] != 'xinput')
        for event in events:
            key = event['backend'], event['slot']
            if event['kind'] == 'input_unavailable':
                self.captures.pop(key, None)
                self.capture.status = 'Controller disconnected. Reconnect it, then press one input.'
                continue
            if event['kind'] == 'input_device':
                calibration = self.detected_calibration(event)
                if calibration is None:
                    self.capture.status = 'Unsupported controller layout. Enable Steam Input for Nioh, then try again.'
                    continue
                self.captures[key] = (BindingCapture(calibration), calibration)
            candidate = self.captures.get(key)
            if not candidate:
                continue
            result = candidate[0].process(event)
            if result:
                self.cancel_capture()
                return dict(result, calibration=candidate[1])
        if self.captures:
            return dict(status='Press one input' if any(candidate[0].neutral for candidate in self.captures.values()) else 'Release all buttons, then press one input')
        return dict(status=self.capture.status if events else 'No supported controller detected. Connect it or enable Steam Input.')

    def dispatch(self, method, params):
        # Dispatch a fixed set of configuration operations instead of evaluating renderer code.
        # File paths reach this worker only through main-process open/save dialogs.
        # TODO(pack-registry): replace sword-only capability discovery after Engine exposes reviewed weapon manifests.
        if os.environ.get('MWM_UI_SMOKE') == '1' and method in ('enable', 'disable', 'capture_start', 'capture_poll', 'preset_switch', 'preset_cycle', 'preset_hotkey_poll'):
            raise ValueError('Game and controller operations are disabled during the packaged UI check')
        if method == 'snapshot':
            return self.snapshot()
        if method == 'preset_list':
            return self.preset_list()
        if method == 'preset_save':
            return self.preset_save(params)
        if method == 'preset_load':
            return self.preset_load(params)
        if method == 'preset_delete':
            return self.preset_delete(params)
        if method == 'preset_cycle':
            return self.preset_cycle(params)
        if method == 'preset_switch':
            return self.preset_switch(params)
        if method == 'preset_hotkey_poll':
            return self.preset_hotkey_poll()
        if method == 'validate':
            return self.validate(params)
        if method == 'preview':
            return self.preview(params)
        if method == 'add_override':
            return self.add_override(params)
        if method == 'apply':
            return self.apply(params)
        if method == 'baseline':
            return trainer.remap_preset(validate_preset(read_json(trainer.ROOT/'data/presets/sword-original.json')),
                                       read_json(trainer.ROOT/'data/controller-calibration.json'), params['calibration'])
        if method == 'starter':
            return trainer.remap_preset(validate_preset(read_json(trainer.ROOT/'data/presets/sword-rebuild-1-supported.json')),
                                       read_json(trainer.ROOT/'data/controller-calibration.json'), params['calibration'])
        if method == 'trial':
            return trainer.remap_preset(validate_preset(read_json(trainer.ROOT/'data/presets/sword-rebuild-1.json')),
                                       read_json(trainer.ROOT/'data/controller-calibration.json'), params['calibration'])
        if method == 'controller':
            choice = params['choice']
            if choice not in ('saved', 'ds4', 'detected', '1', '2', '3', '4'):
                raise ValueError('Choose a saved mapping, detected pad, DS4 or XInput controller 1–4')
            calibration = (self.snapshot()['calibration'] if choice == 'saved' else
                           read_json(trainer.ROOT/'data/controller-calibration.json') if choice == 'ds4' else
                           params['detected_calibration'] if choice == 'detected' else
                           self.xinput_calibration(int(choice)-1))
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
        if method == 'haptic':
            return haptic_pulse(params.get('slot'))
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
                validation = isinstance(error, BindingError) or (isinstance(error, ValueError) and not isinstance(error, json.JSONDecodeError)
                    and request.get('method') in ('preview', 'validate', 'add_override', 'binding_import', 'import', 'controller', 'preset_save', 'preset_load'))
                reply = dict(id=request.get('id'), error=dict(kind='validation' if validation else 'operation', message=str(error)))
            print(json.dumps(reply, allow_nan=False), flush=True)
    finally:
        desktop.cancel_capture()


if __name__ == '__main__':
    main()
