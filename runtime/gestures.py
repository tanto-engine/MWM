# Recognize configured sword gestures using saved controller identities.
import math
from move_imports import IMPORT_LIMIT


def identity(event):
    # Select the stable capability fields retained in a mapping.
    # Omit observation timing and transient button state.
    # Compare reconnects against the same device description.
    keys = ("backend", "slot", "name", "manufacturer", "product", "num_buttons",
            "num_axes", "axis_ranges", "caps_result")
    return {key: event[key] for key in keys if key in event}



class ControllerGesture:
    def __init__(self, calibration, binding, frequency, string_variant=None):
        # Create the tap/hold and held-string input state machine.
        # Validate the saved chord and convert seconds to the trace clock.
        # No gesture is eligible until its controls have been released.
        self.device = calibration['device']
        if binding['device'] != self.device or binding['lb_mask'] != calibration['lb_mask']:
            raise ValueError('Binding does not match the saved controller')
        self.lb_mask = binding.get('modifier_mask', binding['lb_mask'])
        self.circle_mask = binding.get('trigger_mask', binding['circle_mask'])
        for bit in (self.lb_mask, self.circle_mask):
            if not isinstance(bit, int) or isinstance(bit, bool) or not 0 < bit <= 0x80000000 or bit & (bit-1):
                raise ValueError('Bindings must be single controller button bits')
        if self.lb_mask == self.circle_mask:
            raise ValueError('Chord buttons must differ')
        seconds = binding['hold_seconds']
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or not .08 <= seconds <= 2:
            raise ValueError('Invalid hold threshold')
        if not isinstance(frequency, (int, float)) or not math.isfinite(frequency) or frequency <= 0:
            raise ValueError('Invalid input clock')
        self.variants = binding.get('variants', [0, 1])
        if not isinstance(self.variants, list) or len(self.variants) != 2 or any(v is not None and (type(v) is not int or not 0<=v<IMPORT_LIMIT) for v in self.variants):
            raise ValueError('Unknown move variant')
        self.frequency = frequency
        self.threshold = int(binding['hold_seconds'] * frequency)
        self.connected = self.neutral_seen = False
        self.lb = self.circle = False
        self.started = 0
        self.fired = False
        self.chord_sequence = self.edge = self.expires = 0
        self.variant = 0
        self.pending = False
        if type(binding.get('string_enabled', True)) is not bool:
            raise ValueError('String binding enable flag must be boolean')
        self.string_variant = string_variant if binding.get('string_enabled', True) else None
        self.trigger_neutral = self.string_held = False
        self.triggers = (False, False)

    def reset(self):
        # Discard gesture state after a discontinuity or invalid context.
        # Clear press timing, pending intent and both neutral-observation latches.
        # A held button cannot carry an old press across reconnection.
        self.neutral_seen = self.pending = False
        self.started = self.edge = self.expires = 0
        self.fired = False
        self.lb = self.circle = False
        self.trigger_neutral = self.string_held = False
        self.triggers = (False, False)

    def emit_intent(self, now, variant):
        # Publish exactly one enabled tap or hold choice.
        # Advance the chord sequence and attach a short expiration deadline.
        # Disabled variants cancel intent rather than selecting a fallback move.
        variant = self.variants[variant]
        if variant is None:
            self.pending = False
            return
        self.chord_sequence += 1
        self.edge, self.expires = now, now + int(.4 * self.frequency)
        self.pending, self.variant = True, variant

    def process(self, event, now, context_valid=True):
        # Turn ordered input samples into release/hold gestures.
        # Gate identity and context, apply trigger hysteresis, then track chord edges.
        # Reconnects and either-trigger release cannot continue an old string.
        if not context_valid:
            self.reset()
        if (event.get('backend'), event.get('slot')) != (self.device['backend'], self.device['slot']):
            return None
        if event['kind'] == 'input_device':
            self.reset()
            self.connected = identity(event) == self.device
            return dict(kind='device_match', accepted=self.connected)
        if event['kind'] == 'input_unavailable':
            self.connected = False
            self.reset()
            return dict(kind='device_unavailable')
        if event['kind'] != 'input':
            return None
        buttons = event.get('buttons')
        if (not self.connected or not context_valid or not isinstance(buttons, int)
                or isinstance(buttons, bool) or not 0 <= buttons <= 0xffffffff):
            self.reset()
            return None
        if event.get('edge_basis') == 'unknown':
            self.reset()
        if self.string_variant is not None:
            axes = event['axes']
            values = axes['lt'], axes['rt']
            if any(type(value) is not int or not 0 <= value <= 255 for value in values):
                self.reset()
                return None
            previous = self.triggers
            self.triggers = tuple(value > (96 if held else 127) for value,held in zip(values,previous))
            held = all(self.triggers)
            if not any(self.triggers):
                self.trigger_neutral = True
            if held and not all(previous) and self.trigger_neutral:
                self.chord_sequence += 1
                self.edge, self.expires = now, now+int(.4*self.frequency)
                self.variant, self.pending = self.string_variant, True
                self.started = 0
                self.trigger_neutral = False
                self.string_held = True
            elif not held and self.string_held:
                self.pending = self.string_held = False
            if self.string_held:
                return dict(kind='logical_input', connected=True, lt=True, rt=True,
                            chord_sequence=self.chord_sequence)
        if buttons & ~(self.lb_mask | self.circle_mask):
            self.reset()
            return None
        lb, circle = bool(buttons & self.lb_mask), bool(buttons & self.circle_mask)
        if not circle:
            if self.started and not self.fired:
                # Classify by elapsed duration even if the release poll arrives
                # just after threshold; never publish tap and hold together.
                self.emit_intent(now, int(now - self.started >= self.threshold))
            self.neutral_seen = True
            self.started = 0
            self.fired = False
        elif not lb:
            self.started = 0
            self.neutral_seen = False
        elif self.neutral_seen and not self.started and not self.circle:
            self.started = now
            self.neutral_seen = False
        self.lb, self.circle = lb, circle
        return dict(kind='logical_input', lb=lb, circle=circle, connected=self.connected,
                    context_valid=context_valid, gesture_started=self.started,
                    chord_sequence=self.chord_sequence)

    def fields(self, now):
        # Expose the current intent to the native command publisher.
        # Resolve a reached hold threshold and expire old pending requests.
        # The native reader receives bounded intent rather than persistent presses.
        if self.started and self.lb and self.circle and not self.fired and now-self.started >= self.threshold:
            self.emit_intent(now, 1)
            self.fired = True
        if now >= self.expires:
            self.pending = False
        return dict(heartbeat=now, edge=self.edge, expires=self.expires,
                    chord_sequence=self.chord_sequence, armed=self.pending,
                    held=self.string_held if self.variant == self.string_variant else self.lb and self.circle,
                    latched=0 if self.variant == self.string_variant else 1, variant=self.variant)

    def dispatched(self, repeat=True):
        # Consume the pending gesture after native acceptance.
        # Clear its armed state while retaining the physical hold information.
        # A single press cannot repeatedly enqueue the same move.
        self.pending = False
