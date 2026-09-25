# Read the controller observations published by the native player frame.
# TODO: Verify physical DualSense, Xbox and SCUF reconnects through Nioh's
# XInput path. DirectInput-only pads and unmapped paddles need explicit support.
# TODO: Add explicit pad selection when multiple XInput slots are connected.
import ctypes as C
import struct
import time

INPUT = struct.Struct('<qq4I4H4B4B4I')
assert INPUT.size == 64

# Windows HID button usages for DS4, expressed in the saved WinMM mask space.
# Steam's conventional XInput face/shoulder names retain the existing bindings.
DS4_BUTTONS = ((0x4000, 1), (0x1000, 2), (0x2000, 4), (0x8000, 8),
               (0x0100, 16), (0x0200, 32), (0x0020, 256), (0x0010, 512),
               (0x0040, 1024), (0x0080, 2048))

BUTTON_LABELS = {0x100:'L1 / LB', 0x200:'R1 / RB', 0x1000:'Cross / A',
                 0x2000:'Circle / B', 0x4000:'Square / X', 0x8000:'Triangle / Y',
                 0x10:'Options / Menu', 0x20:'Share / View', 0x40:'L3', 0x80:'R3',
                 1:'D-pad up', 2:'D-pad down', 4:'D-pad left', 8:'D-pad right'}
GAME_DEVICE = dict(backend='xinput', slot=0, name='Nioh game controller')


def game_button_mask(device, mask):
    # Translate a saved button identity into Nioh's XInput namespace.
    # Accept native masks or match the known calibrated DS4 mask table.
    # Unknown saved layouts fail rather than guessing a physical button.
    if device['backend'] == 'xinput':
        if mask not in BUTTON_LABELS:
            raise ValueError('Binding is not a standard gamepad button')
        return mask
    # This translates an existing saved mapping, not the currently attached
    # hardware. DS4, DualSense, Xbox and compatible pads all arrive through the
    # same game-facing protocol, so swapping hardware requires no calibration.
    saved_buttons(device, 0, 0, 0)
    for native, saved in DS4_BUTTONS:
        if mask == saved:
            return native
    raise ValueError('Saved binding has no standard gamepad equivalent')


def game_binding(calibration, binding):
    # Compile saved logical controls for the game's input stream.
    # Check mapping identity and translate both chord masks once.
    # Changing compatible hardware does not require repeated calibration.
    if binding['device'] != calibration['device'] or binding['lb_mask'] != calibration['lb_mask']:
        raise ValueError('Binding differs from its saved mapping')
    device = calibration['device']
    lb = game_button_mask(device, calibration['lb_mask'])
    compiled = dict(binding, device=GAME_DEVICE, lb_mask=lb,
                    modifier_mask=game_button_mask(device, binding.get('modifier_mask', binding['lb_mask'])),
                    trigger_mask=game_button_mask(device, binding.get('trigger_mask', binding['circle_mask'])))
    compiled['circle_mask'] = compiled['trigger_mask']
    return dict(calibration, device=GAME_DEVICE, lb_mask=lb), compiled


def binding_buttons(device):
    # Expose readable choices in the saved binding namespace.
    # Project either native XInput labels or supported DS4 equivalents.
    # UI selections remain consistent with the stored masks.
    if device['backend'] == 'xinput':
        return {label: mask for mask, label in BUTTON_LABELS.items()}
    saved_buttons(device, 0, 0, 0)
    return {BUTTON_LABELS[native]: saved for native, saved in DS4_BUTTONS}


def saved_buttons(device, buttons, lt, rt):
    # Convert game-facing input back to a supported saved layout.
    # Map face/shoulder bits and threshold the two analog triggers.
    # Unsupported saved device layouts cannot fabricate logical presses.
    if device['backend'] == 'xinput':
        return buttons
    if (device['backend'], device['manufacturer'], device['product']) not in (
            ('winmm', 0x054c, 0x09cc), ('winmm', 0x054c, 0x05c4)):
        raise ValueError('No game-input translation for this saved controller')
    result = sum(mask for source, mask in DS4_BUTTONS if buttons & source)
    return result | (64 if lt >= 128 else 0) | (128 if rt >= 128 else 0)


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
        saved_buttons(self.device, 0, 0, 0)
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
        if len(connected) != 1:
            self.detection = 'multiple game controllers; selection ambiguous' if connected else 'no game controller connected'
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
        axes = {'lt': lt, 'rt': rt} if self.name == 'xinput' else {'v': lt*257, 'u': rt*257}
        return 0, dict(buttons=saved_buttons(self.device, buttons, lt, rt), axes=axes,
                       pov=None, packet=values[18+index], transport='game_xinput', source_slot=index,
                       sample_qpc=values[1], button_labels=[label for bit, label in BUTTON_LABELS.items() if buttons & bit])
