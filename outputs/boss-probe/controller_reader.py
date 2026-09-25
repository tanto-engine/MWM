# Read-only OS controller observations, separate from game-accepted input.
#
# WinMM button numbers deliberately have no guessed physical/game labels.
# Queries do not acquire, capture, or write to devices. No game APIs are used.
import ctypes as C
from ctypes import wintypes as W
import time


XINPUT_BUTTONS = {
    0x0001: "dpad_up", 0x0002: "dpad_down", 0x0004: "dpad_left",
    0x0008: "dpad_right", 0x0010: "start", 0x0020: "back",
    0x0040: "left_stick", 0x0080: "right_stick", 0x0100: "lb",
    0x0200: "rb", 0x1000: "a", 0x2000: "b", 0x4000: "x", 0x8000: "y",
}


class JoyInfo(C.Structure):
    _fields_ = [(name, W.DWORD) for name in (
        "size", "flags", "x", "y", "z", "r", "u", "v", "buttons",
        "button_number", "pov", "reserved1", "reserved2")]


class JoyCaps(C.Structure):
    _fields_ = [("manufacturer", W.WORD), ("product", W.WORD), ("name", W.WCHAR * 32)] + [
        (name, W.UINT) for name in (
            "xmin", "xmax", "ymin", "ymax", "zmin", "zmax", "num_buttons",
            "period_min", "period_max", "rmin", "rmax", "umin", "umax",
            "vmin", "vmax", "caps", "max_axes", "num_axes", "max_buttons")
    ] + [("regkey", W.WCHAR * 32), ("oem", W.WCHAR * 260)]


class Gamepad(C.Structure):
    _fields_ = [("buttons", W.WORD), ("lt", W.BYTE), ("rt", W.BYTE)] + [
        (name, C.c_short) for name in ("lx", "ly", "rx", "ry")]


class XInputState(C.Structure):
    _fields_ = [("packet", W.DWORD), ("pad", Gamepad)]


class WinMMBackend:
    name = "winmm"
    # Missing driver, absent slot, or unplugged joystick are expected absence.
    absent_codes = {2, 6, 167}

    def __init__(self):
        # Bind WinMM with the Windows structure layout expected by its ABI.
        # Warm the driver and cache capabilities before recording starts.
        # Keep driver initialization latency outside encounter timestamps.
        assert C.sizeof(JoyInfo) == 52 and C.sizeof(JoyCaps) == 728
        self.dll = C.WinDLL("winmm")
        self.dll.joyGetNumDevs.restype = W.UINT
        self.dll.joyGetDevCapsW.argtypes = [C.c_size_t, C.POINTER(JoyCaps), W.UINT]
        self.dll.joyGetDevCapsW.restype = W.UINT
        self.dll.joyGetPosEx.argtypes = [W.UINT, C.POINTER(JoyInfo)]
        self.dll.joyGetPosEx.restype = W.UINT
        self._caps = {}
        self.capability_codes = {}
        # The first WinMM query may initialize its driver stack. Do that while
        # constructing the reader, before the caller starts the recording clock.
        self.slots()

    def slots(self):
        # Find slots with advertised capabilities instead of probing every position.
        # Refresh the capability cache on each discovery pass.
        # Avoid driver timeouts on empty joystick slots.
        eligible = []
        # joyGetNumDevs reports supported slots, not connected controllers.
        # Query capabilities first: reading position on every empty slot can
        # incur driver timeouts and produces JOYERR_PARMS (165) on this system.
        # WinMM joystick identifiers are 0..15. Connected slots are still polled
        # independently by ControllerReader, even if a later capability query fails.
        for slot in range(min(16, self.dll.joyGetNumDevs())):
            caps = JoyCaps()
            code = self.dll.joyGetDevCapsW(slot, C.byref(caps), C.sizeof(caps))
            self.capability_codes[slot] = code
            if code == 0:
                self._caps[slot] = caps
                eligible.append(slot)
            else:
                self._caps.pop(slot, None)
        return eligible

    def read(self, slot):
        # Read one joystick snapshot through joyGetPosEx.
        # Return raw axes and button bits alongside the native result code.
        # Leave physical labels to saved device mappings.
        state = JoyInfo()
        state.size, state.flags = C.sizeof(state), 0xFF  # JOY_RETURNALL
        code = self.dll.joyGetPosEx(slot, C.byref(state))
        if code:
            return code, None
        return 0, dict(buttons=state.buttons, pov=state.pov,
                       axes={name: getattr(state, name) for name in ("x", "y", "z", "r", "u", "v")})

    def describe(self, slot):
        # Expose device identity and advertised axis limits.
        # Reuse cached capabilities or query the requested slot once.
        # Retain capability errors so unsupported devices remain diagnosable.
        caps = self._caps.get(slot)
        code = 0
        if caps is None:
            caps = JoyCaps()
            code = self.dll.joyGetDevCapsW(slot, C.byref(caps), C.sizeof(caps))
        result = dict(caps_result=code, button_labels="uncalibrated 1-based bit indices",
                      axis_units="raw WinMM values; ranges are device specific",
                      pov_units="hundredths of a degree; 65535 is centered")
        if code == 0:
            result.update(name=caps.name, manufacturer=caps.manufacturer, product=caps.product,
                          num_buttons=caps.num_buttons, num_axes=caps.num_axes,
                          axis_ranges={name: [getattr(caps, name + "min"), getattr(caps, name + "max")]
                                       for name in ("x", "y", "z", "r", "u", "v")})
        return result


class XInputBackend:
    name = "xinput"
    absent_codes = {1167}  # ERROR_DEVICE_NOT_CONNECTED

    def __init__(self):
        # Bind the XInput state query with its fixed Windows ABI.
        # Check the packed state size before any native read.
        # Use the OS backend without acquiring the controller.
        assert C.sizeof(XInputState) == 16
        self.dll = C.WinDLL("xinput1_4")
        self.dll.XInputGetState.argtypes = [W.DWORD, C.POINTER(XInputState)]
        self.dll.XInputGetState.restype = W.DWORD

    def slots(self):
        # Expose the four slots defined by XInput.
        # Connection checks happen when each slot is read.
        # Avoid confusing supported slots with attached devices.
        return range(4)

    def read(self, slot):
        # Sample one XInput controller into a native state structure.
        # Decode standardized buttons, triggers and sticks on success.
        # Preserve disconnect codes rather than inventing neutral input.
        state = XInputState()
        code = self.dll.XInputGetState(slot, C.byref(state))
        if code:
            return code, None
        pad = state.pad
        return 0, dict(buttons=pad.buttons, pov=None, packet=state.packet,
                       axes={name: getattr(pad, name) for name in ("lt", "rt", "lx", "ly", "rx", "ry")},
                       button_names_down=[name for mask, name in XINPUT_BUTTONS.items() if mask & pad.buttons])

    def describe(self, slot):
        # Describe the standardized XInput axes and button labels.
        # No device-specific calibration is needed for these raw ranges.
        # Game bindings remain separate from conventional button names.
        return dict(button_labels="conventional XInput names; game function uncalibrated",
                    axis_units="lt/rt: 0..255; sticks: -32768..32767", pov_units=None)


class ControllerReader:
    # Poll connected slots each call; discover/retry absent slots every two seconds.
    #
    # Events retain raw axes, with coarse buckets suppressing axis-only jitter.
    # Button and POV changes are never bucketed. Polling can miss brief events.
    # Initial/recovery observations have unknown edges, never fabricated presses.
    # A physical controller may appear in both backends; streams are not deduplicated.
    # Optional backends/clock are seams for tests that never access a controller.
    def __init__(self, backends=None, clock=time.perf_counter, rescan_seconds=2.0):
        # Create independent backend streams with a shared sampling clock.
        # Track previous observations and rescan deadlines per reader.
        # Keep optional driver failures visible without disabling other backends.
        if rescan_seconds < 0.1:
            raise ValueError("Rescan interval must be at least 0.1 seconds")
        self._clock = clock
        self._rescan_seconds = rescan_seconds
        self._next_rescan = float("-inf")
        self._load_errors = {}
        if backends is None:
            backends = []
            for factory in (WinMMBackend, XInputBackend):
                try:
                    backends.append(factory())
                except OSError as exc:
                    self._load_errors[factory.name] = str(exc)
        self._backends = list(backends)
        self._active = set()
        self._last = {}
        self._last_error = {}
        self._last_codes = {}
        self._edges = self._events = self._disconnects = self._errors = 0
        self._polls = 0

    @staticmethod
    def input_change_key(backend, state):
        # Quantize axes solely for change detection.
        # Preserve exact button and POV values in the comparison key.
        # Suppress analog jitter without losing digital edges.
        axes = state["axes"]
        buckets = tuple((name, round(value / (16 if backend == "xinput" and name in ("lt", "rt") else 4096)))
                        for name, value in sorted(axes.items()))
        return state["buttons"], state.get("pov"), buckets

    def poll(self):
        # Poll connected slots and periodically search for returning devices.
        # Derive edges only when a prior observation exists for that stream.
        # Discard history on disconnect so reconnects cannot fabricate presses.
        now = self._clock()
        rescan = now >= self._next_rescan
        if rescan:
            self._next_rescan = now + self._rescan_seconds
        events = []
        self._polls += 1
        for backend in self._backends:
            slots = {slot for name, slot in self._active if name == backend.name}
            if rescan:
                slots.update(backend.slots())
            for slot in sorted(slots):
                key = (backend.name, slot)
                code, state = backend.read(slot)
                observed = self._clock()
                self._last_codes[key] = code
                common = dict(backend=backend.name, slot=slot, observed_monotonic=observed)
                if code:
                    was_active = key in self._active
                    unexpected = code not in backend.absent_codes
                    changed_error = self._last_error.get(key) != code
                    if was_active or (unexpected and changed_error):
                        events.append(dict(kind="input_unavailable", code=code,
                                           was_available=was_active, expected_absence=not unexpected,
                                           pressed_mask=None, released_mask=None, **common))
                    if unexpected and changed_error:
                        self._errors += 1
                    if was_active:
                        self._disconnects += 1
                    self._active.discard(key)
                    self._last.pop(key, None)
                    self._last_error[key] = code
                    continue
                if key not in self._active:
                    events.append(dict(kind="input_device", **common, **backend.describe(slot)))
                self._active.add(key)
                self._last_error.pop(key, None)
                change_key = self.input_change_key(backend.name, state)
                prior = self._last.get(key)
                # A reconnect establishes a new baseline. Unknown edges remain
                # None until a second observation can establish an actual change.
                if prior is not None and prior == change_key:
                    continue
                buttons = state["buttons"]
                old_buttons = prior[0] if prior is not None else None
                pressed = buttons & ~old_buttons if old_buttons is not None else None
                released = old_buttons & ~buttons if old_buttons is not None else None
                if pressed is not None:
                    self._edges += pressed.bit_count() + released.bit_count()
                events.append(dict(kind="input", **common, **state,
                                   buttons_down=[i + 1 for i in range(32) if buttons & (1 << i)],
                                   pressed_mask=pressed, released_mask=released,
                                   edge_basis="previous_observation" if prior is not None else "unknown"))
                self._last[key] = change_key
                self._events += 1
        return events

    def status(self):
        # Summarize reader counters and native backend errors.
        # Report connected slots separately from capability results.
        # Expose polling limitations for interpreting recorded evidence.
        names = {backend.name for backend in self._backends} | set(self._load_errors)
        return dict(valid_slots={name: sorted(slot for backend, slot in self._active if backend == name)
                                 for name in sorted(names)},
                    backend_load_errors=dict(self._load_errors), unexpected_error_events=self._errors,
                    capability_result_codes={backend.name: dict(backend.capability_codes)
                                             for backend in self._backends if hasattr(backend, "capability_codes")},
                    disconnect_events=self._disconnects, button_edges=self._edges,
                    input_events=self._events, polls=self._polls,
                    last_result_codes={f"{name}:{slot}": code for (name, slot), code in sorted(self._last_codes.items())},
                    rescan_seconds=self._rescan_seconds,
                    button_mapping="uncalibrated; OS observations are not game-accepted input",
                    cross_backend_duplicates_possible=True)
