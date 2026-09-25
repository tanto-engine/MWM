# Portable movesets. Stable move identifiers, never process addresses.
import copy
import json
import math
import os
from pathlib import Path
import tempfile
import time

if os.name == 'nt':
    import ctypes as C
    from ctypes import wintypes as W
    import msvcrt
    kernel = C.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [W.LPCWSTR, W.DWORD, W.DWORD, C.c_void_p, W.DWORD, W.DWORD, W.HANDLE]
    kernel.CreateFileW.restype = W.HANDLE
    kernel.CloseHandle.argtypes = [W.HANDLE]
    kernel.ReplaceFileW.argtypes = [W.LPCWSTR, W.LPCWSTR, W.LPCWSTR, W.DWORD, C.c_void_p, C.c_void_p]
    kernel.ReplaceFileW.restype = W.BOOL

# Native signatures and resource indices belong to imports, saved device masks to calibration.
# TODO: gameplay acceptance remains separate from validation of a supported preset.
MOVE_VARIANTS = {'okatsu.charged_rush': 0, 'okatsu.leaping_slash': 1}
HEAVY_STRINGS = {'jin_hayabusa.action_0bc0': 'C', 'jin_hayabusa.action_0c6e': 'D'}
HELD_MOVES = {'jin_hayabusa.action_0c79', 'jin_hayabusa.action_0cac'}
DEFAULT_PRESET = dict(schema_version=3, name='Sword baseline', weapon='sword',
                      tap_move='okatsu.charged_rush', hold_move='okatsu.leaping_slash',
                      modifier_mask=16, trigger_mask=4, hold_seconds=.25,
                      low_heavy='jin_hayabusa.action_0c6e',
                      stance_holds=dict(low='jin_hayabusa.action_0c79', mid=None, high=None),
                      okatsu_grapple=True, tiger_sprint=True, mid_light_ender=True, string_enabled=False,
                      high_guard_light='jin_hayabusa.action_0c81',
                      frost_moon=dict(low='jin_hayabusa.action_0c71', mid='jin_hayabusa.izuna_drop', high='jin_hayabusa.action_0cac'),
                      frost_window_seconds=.75, frost_startup_speed=8)


def atomic_json(path, value):
    # Publish runtime state while Windows readers hold shared handles.
    # Serialize to a sibling file and use bounded atomic replacement.
    # Sharing races are retried; unrelated write failures remain visible.
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf8', dir=path.parent,
                                         prefix=path.name+'.', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, indent=2, allow_nan=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        # ReplaceFileW can replace a destination held by share-delete readers;
        # MoveFileEx (Path.replace) rejects that overlap on Windows. Legacy
        # readers without delete sharing get a short, bounded retry.
        for attempt in range(6):
            try:
                if os.name == 'nt':
                    if not kernel.ReplaceFileW(str(path), str(temporary), None, 0, None, None):
                        error = C.get_last_error()
                        if error != 2:  # A new destination has no file to replace.
                            raise C.WinError(error)
                        temporary.replace(path)
                else:
                    temporary.replace(path)
                break
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(.005)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def read_json(path, default=None):
    # Read state files without blocking an atomic Windows replacement.
    # Open with delete sharing and bound retries for transient name/lock gaps.
    # Only genuine absence returns the caller's explicit default.
    try:
        if os.name == 'nt':
            # Atomic replacement requires delete sharing in both directions:
            # readers must coexist with the writer's temporary DELETE handle.
            for attempt in range(6):
                handle = kernel.CreateFileW(str(Path(path)), 0x80000000, 7, None, 3, 0x80, None)
                if handle != C.c_void_p(-1).value:
                    break
                error = C.get_last_error()
                # Replacement briefly locks the new file and can leave a name
                # gap. Genuine absence still returns the caller's default after
                # this bounded window; access denials are never retried.
                if error not in (2, 32) or attempt == 5:
                    raise C.WinError(error)
                time.sleep(.005)
            try:
                descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY)
            except OSError:
                kernel.CloseHandle(handle)
                raise
            with os.fdopen(descriptor, 'r', encoding='utf-8-sig') as stream:
                return json.load(stream)
        return json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except FileNotFoundError:
        return copy.deepcopy(default)


def validate_preset(value):
    # Reject movesets the current runtime cannot execute.
    # Check schema, implemented move IDs, distinct button bits and hold time.
    # Corrupt settings cannot silently become a different binding.
    if not isinstance(value, dict) or type(value.get('schema_version')) is not int or value['schema_version'] != 3:
        raise ValueError('Unsupported moveset version')
    missing = [key for key in DEFAULT_PRESET if key not in value]
    if missing:
        raise ValueError('Incomplete moveset: missing ' + ', '.join(missing))
    if set(value) != set(DEFAULT_PRESET):
        raise ValueError('Unknown preset fields: ' + ', '.join(sorted(set(value)-set(DEFAULT_PRESET))))
    result = copy.deepcopy(value)
    if not isinstance(result['name'], str) or not result['name'].strip() or len(result['name']) > 100:
        raise ValueError('Give the moveset a name of 1 to 100 characters')
    for key in ('tap_move', 'hold_move'):
        if result[key] is not None and (not isinstance(result[key], str) or result[key] not in MOVE_VARIANTS):
            raise ValueError('This move has no implemented runtime adapter: ' + str(result[key]))
    for key in ('modifier_mask', 'trigger_mask'):
        bit = result[key]
        if not isinstance(bit, int) or isinstance(bit, bool) or not 0 < bit <= 0x80000000 or bit & (bit-1):
            raise ValueError('Choose one controller button for each part of the chord')
    if result['modifier_mask'] == result['trigger_mask']:
        raise ValueError('Modifier and trigger must be different buttons')
    seconds = result['hold_seconds']
    if isinstance(seconds, bool) or not isinstance(seconds, (float, int)) or not math.isfinite(seconds) or not .08 <= seconds <= 2:
        raise ValueError('Hold threshold must be between 0.08 and 2 seconds')
    if result['weapon'] != 'sword' or result['low_heavy'] not in (None, *HEAVY_STRINGS):
        raise ValueError('Choose a supported sword string for low Triangle')
    if result['high_guard_light'] not in (None, 'jin_hayabusa.action_0c81'):
        raise ValueError('High LB + Square requires Jin somersault or Native')
    holds=result['stance_holds']
    if not isinstance(holds, dict) or set(holds) != {'low','mid','high'}:
        raise ValueError('Held Triangle requires low, mid and high entries')
    enabled=[move for move in holds.values() if move is not None]
    if any(not isinstance(move,str) or move not in HELD_MOVES for move in enabled):
        raise ValueError('Held Triangle requires a standalone sword move')
    if len(enabled) != len(set(enabled)):
        raise ValueError('Stance holds cannot duplicate imports')
    frost=result['frost_moon']
    if not isinstance(frost,dict) or set(frost)!=set(holds):
        raise ValueError('Frost Moon requires low, mid and high entries')
    for stance,identifier in frost.items():
        if identifier not in (None,'jin_hayabusa.action_0cac','jin_hayabusa.izuna_drop','jin_hayabusa.action_0c71'):
            raise ValueError('Frost Moon requires a supported sword skill')
        if identifier=='jin_hayabusa.izuna_drop' and stance!='mid':
            raise ValueError('Izuna Drop requires the mid-stance Frost Moon binding')
        if identifier=='jin_hayabusa.action_0c71' and stance!='low':
            raise ValueError('Flying Swallow requires the low-stance Frost Moon binding')
        if identifier and any(value==identifier and other!=stance for other,value in (*holds.items(),*frost.items())):
            raise ValueError('A skill must use the same stance across bindings')
    seconds=result['frost_window_seconds']
    if type(seconds) not in (int,float) or not math.isfinite(seconds) or not .1<=seconds<=1.5:
        raise ValueError('Frost Moon window must be between 0.1 and 1.5 seconds')
    if type(result['frost_startup_speed']) is not int or not 1<=result['frost_startup_speed']<=8:
        raise ValueError('Frost Moon startup speed must be an integer from 1 to 8')
    if any(type(result[key]) is not bool for key in ('okatsu_grapple','tiger_sprint','mid_light_ender','string_enabled')):
        raise ValueError('Grapple and string enable flags must be boolean')
    return result


def binding_for_preset(calibration, preset):
    # Combine a portable moveset with the saved device mapping.
    # Validate the preset and translate stable move IDs into runtime variants.
    # Session addresses never become part of a saved moveset.
    preset = validate_preset(preset)
    return dict(schema=1, device=copy.deepcopy(calibration['device']),
                  lb_mask=calibration['lb_mask'], circle_mask=preset['trigger_mask'],
                  modifier_mask=preset['modifier_mask'], trigger_mask=preset['trigger_mask'],
                  hold_seconds=preset['hold_seconds'], moveset=preset,
                  string_enabled=preset['string_enabled'],
                  variants=[MOVE_VARIANTS.get(preset['tap_move']), MOVE_VARIANTS.get(preset['hold_move'])])
