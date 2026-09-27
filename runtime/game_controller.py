# Read the controller observations published by the native player frame.
# Physical-device acceptance is separate from protocol support. DirectInput-only
# pads need a game-facing XInput translation; paddles may expose no distinct bit.
import ctypes as C
import struct
import time
from controller_reader import logical_buttons
from gestures import identity

INPUT = struct.Struct('<qq4I4H4B4B4I')
assert INPUT.size == 64

# Windows HID button usages for DS4, expressed in the saved WinMM mask space.
# Steam's conventional XInput face/shoulder names retain the existing bindings.
DS4_BUTTONS = ((0x4000, 1), (0x1000, 2), (0x2000, 4), (0x8000, 8),
               (0x0100, 16), (0x0200, 32), (0x0020, 256), (0x0010, 512),
               (0x0040, 1024), (0x0080, 2048), (0x0400, 64), (0x0800, 128))

BUTTON_LABELS = {0x100:'L1 / LB', 0x200:'R1 / RB', 0x1000:'Cross / A',
                 0x2000:'Circle / B', 0x4000:'Square / X', 0x8000:'Triangle / Y',
                 0x10:'Options / Menu', 0x20:'Share / View', 0x40:'L3', 0x80:'R3',
                 1:'D-pad up', 2:'D-pad down', 4:'D-pad left', 8:'D-pad right',
                 0x400:'L2 / LT', 0x800:'R2 / RT'}
GAME_DEVICE = dict(backend='xinput', slot=0, name='Nioh game controller')


def controller_selection(calibration):
    # Convert the selected controller into the native session's numbering scheme.
    # Python uses slots 0–3; the native value reserves 0 for automatic selection and uses 1–4 for explicit slots.
    # Reject unsupported slot values before a different player's controller could be selected.
    slot = calibration.get('controller_slot')
    if slot is not None and (type(slot) is not int or not 0 <= slot < 4):
        raise ValueError('Choose automatic selection or XInput controller 1 to 4')
    return 0 if slot is None else slot + 1


def _button_map(device, button_map=None):
    # Translate a controller's saved button bits into Nioh-facing logical buttons.
    # XInput is already logical; WinMM needs a reviewed DS4 layout or an explicit one-to-one calibration.
    # Distinct power-of-two bits prevent two controls from silently becoming the same binding.
    if device['backend'] == 'xinput':
        return {bit:bit for bit in BUTTON_LABELS}
    if device['backend'] != 'winmm':
        raise ValueError('Unsupported controller backend; game input requires XInput')
    if button_map is not None:
        if not isinstance(button_map, dict) or not button_map:
            raise ValueError('Calibrated button map must contain raw-to-logical button bits')
        result = {}
        for raw, logical in button_map.items():
            raw = int(raw) if isinstance(raw, str) and raw.isdecimal() else raw
            if (type(raw) is not int or not 0 < raw <= 0x80000000 or raw & (raw-1)
                    or type(logical) is not int or logical not in BUTTON_LABELS or raw in result
                    or logical in result.values()):
                raise ValueError('Calibrated button map requires distinct single raw and logical bits')
            result[raw] = logical
        return result
    if (device.get('manufacturer'), device.get('product')) in ((0x054c, 0x09cc), (0x054c, 0x05c4)):
        return {saved:native for native, saved in DS4_BUTTONS}
    raise ValueError('This WinMM layout needs an explicit calibrated button map or game-facing XInput')


def game_button_mask(device, mask, button_map=None):
    # Translate one saved button choice into the game's button namespace.
    # Require the exact single-button entry in the selected controller's mapping.
    # An unsupported raw bit raises instead of being guessed from the controller's name.
    mapping = _button_map(device, button_map)
    if type(mask) is not int or mask not in mapping:
        raise ValueError('Saved binding has no standard gamepad equivalent')
    return mapping[mask]


def game_binding(calibration, binding):
    # Compile saved logical controls for the game's input stream.
    # Check mapping identity and translate both chord masks once.
    # Changing compatible hardware does not require repeated calibration.
    if binding['device'] != calibration['device'] or binding['lb_mask'] != calibration['lb_mask']:
        raise ValueError('Binding differs from its saved mapping')
    device = calibration['device']
    mapping = calibration.get('button_map')
    controller_selection(calibration)
    lb = game_button_mask(device, calibration['lb_mask'], mapping)
    compiled = dict(binding, device=GAME_DEVICE, lb_mask=lb,
                    modifier_mask=game_button_mask(device, binding.get('modifier_mask', binding['lb_mask']), mapping),
                    trigger_mask=game_button_mask(device, binding.get('trigger_mask', binding['circle_mask']), mapping))
    compiled['circle_mask'] = compiled['trigger_mask']
    return dict(calibration, device=GAME_DEVICE, lb_mask=lb), compiled


def binding_buttons(device, button_map=None):
    # Expose readable choices in the saved binding namespace.
    # Project either native XInput labels or supported DS4 equivalents.
    # UI selections remain consistent with the stored masks.
    return {BUTTON_LABELS[logical]:raw for raw, logical in _button_map(device, button_map).items()}


def saved_buttons(device, buttons, lt, rt, button_map=None):
    # Convert game-facing input back to a supported saved layout.
    # Map face/shoulder bits and threshold the two analog triggers.
    # Unsupported saved device layouts cannot fabricate logical presses.
    buttons = logical_buttons(buttons, lt, rt)
    return sum(raw for raw, logical in _button_map(device, button_map).items() if buttons & logical)


class BindingCapture:
    """Consume selected controller observations; return one saved/logical button."""
    def __init__(self, calibration):
        # Prepare a temporary listener for one controller's next binding input.
        # Keep its identity and raw-to-logical map together so device changes cannot change button meaning.
        # Reset capture to require a released controller before accepting any press.
        self.device = calibration['device']
        self.mapping = _button_map(self.device, calibration.get('button_map'))
        self.matches = True
        self.reset()

    def reset(self):
        # Start binding again from a neutral controller state.
        # Clear both the release observation and completed-result latch.
        # This prevents held buttons or reconnects from being mistaken for a new deliberate choice.
        self.neutral = self.complete = False
        self.status = 'Release all buttons, then press one input'

    def process(self, event):
        # Accept one deliberate press from the selected controller after all buttons are released.
        # Reject other devices, reconnect gaps, mixed chords and inputs absent from the calibrated map.
        # Return both saved and logical masks; the trainer edits its form without immediately saving a preset.
        if (event.get('backend'), event.get('slot')) != (self.device['backend'], self.device['slot']):
            return None
        if event['kind'] in ('input_device', 'input_unavailable'):
            self.reset()
            self.matches = event['kind'] == 'input_device' and identity(event) == self.device
            self.status = 'Release all buttons, then press one input' if self.matches else 'Selected controller unavailable or changed'
            return None
        if event['kind'] != 'input' or self.complete or not self.matches:
            return None
        if event.get('edge_basis') == 'unknown':
            self.reset()
        buttons = event['buttons']
        if event.get('transport') == 'game_xinput':
            # Do not hide extra inputs absent from a partial saved calibration.
            logical = event['logical_buttons']
            buttons = next((raw for raw, bit in self.mapping.items() if bit == logical), -1) if logical else 0
        elif self.device['backend'] == 'xinput':
            axes = event['axes']
            buttons = logical_buttons(buttons, axes.get('lt', 0), axes.get('rt', 0))
        if not buttons and event.get('pov') in (None, 65535):
            self.neutral = True
            self.status = 'Press one input'
            return None
        if not self.neutral:
            return None
        self.neutral = False
        if buttons not in self.mapping or event.get('pov') not in (None, 65535):
            self.status = 'Release all buttons; use one calibrated input'
            return None
        logical = self.mapping[buttons]
        self.complete = True
        self.status = 'Captured ' + BUTTON_LABELS[logical]
        return dict(mask=buttons, logical_mask=logical, label=BUTTON_LABELS[logical])


class GameController:
    absent_codes = {1167, 1237}

    def __init__(self, trace, calibration):
        # Bind one reader to the native controller observation block.
        # Pin the trace clock and initialize slot/packet tracking.
        # The first sample must establish connection state before an edge exists.
        self.trace = trace
        self.device = calibration['device']
        self.name = self.device['backend']
        self.frequency = trace.header()['frequency']
        self.selection = controller_selection(calibration)
        self.button_map = calibration.get('button_map')
        saved_buttons(self.device, 0, 0, 0, self.button_map)
        self.capability_codes = {}
        self.source_slot = None
        self.packet = None
        self.detection = 'waiting for game controller'

    def slots(self):
        # Present the saved logical device slot to ControllerReader.
        # Return its configured slot independently of the physical XInput index.
        # Reconnects can move hardware without rewriting the binding.
        return [self.device['slot']]

    def describe(self, slot):
        # Describe the native stream using the saved device identity.
        # Add transport and mask-space labels to its existing capabilities.
        # The caller can display input provenance without recalibrating.
        return {**{key: value for key, value in self.device.items() if key not in ('backend', 'slot')},
                'transport': 'game_xinput', 'button_labels': 'saved controller mask space'}

    def read(self, slot):
        # Read one coherent native game-frame controller sample.
        # Check publication markers, age, active slots and packet continuity.
        # Suspension or reconnection returns unavailable instead of a false edge.
        address = self.trace.address + 64
        before = C.c_int64.from_address(address).value
        raw = C.string_at(address, INPUT.size)
        values = INPUT.unpack(raw)
        after = C.c_int64.from_address(address).value
        if not before or before & 1 or before != after or values[0] != before:
            self.detection = 'waiting for a complete game frame'
            return 1237, None
        if not 0 <= time.perf_counter() - values[1] / self.frequency < .1:
            self.detection = 'game frames suspended'
            return 1167, None
        # XInput indices are distinct from WinMM indices. Follow the sole active
        # controller across reconnects; ambiguity must never select another pad.
        connected = [index for index, code in enumerate(values[2:6]) if code == 0]
        if self.selection:
            connected = [self.selection-1] if self.selection-1 in connected else []
        if len(connected) != 1:
            self.detection = (f'selected game controller {self.selection} unavailable' if self.selection else
                              'multiple game controllers; selection ambiguous' if connected else 'no game controller connected')
            if all(code == 127 for code in values[2:6]):
                self.detection = 'game XInput backend unavailable'
            return 1167, None
        index = connected[0]
        previous = self.source_slot
        self.source_slot = index
        packet = values[18+index]
        replaced = previous is not None and (previous != index or self.packet is not None and packet < self.packet)
        self.packet = packet
        if replaced:
            self.detection = 'controller changed; release buttons to resume'
            return 1167, None
        self.detection = f'game controller {index+1} connected (XInput)'
        buttons, lt, rt = values[6+index], values[10+index], values[14+index]
        logical = logical_buttons(buttons, lt, rt)
        axes = {'lt': lt, 'rt': rt} if self.name == 'xinput' else {'v': lt*257, 'u': rt*257}
        return 0, dict(buttons=saved_buttons(self.device, buttons, lt, rt, self.button_map), axes=axes,
                       pov=None, packet=values[18+index], transport='game_xinput', source_slot=index,
                       logical_buttons=logical, sample_qpc=values[1],
                       button_labels=[label for bit, label in BUTTON_LABELS.items() if logical & bit])
