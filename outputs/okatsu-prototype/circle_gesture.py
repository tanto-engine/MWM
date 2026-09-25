"""Persistent DS4 LB+Circle mapping and release/hold gesture recognition."""
from calibrate_controller import identity


class CircleGesture:
    def __init__(self, calibration, binding, frequency):
        self.device = calibration['device']
        if binding['device'] != self.device or binding['lb_mask'] != calibration['lb_mask']:
            raise ValueError('Binding does not match the saved controller')
        self.lb_mask, self.circle_mask = binding['lb_mask'], binding['circle_mask']
        self.frequency = frequency
        self.threshold = int(binding['hold_seconds'] * frequency)
        self.connected = self.neutral_seen = False
        self.lb = self.circle = False
        self.started = 0
        self.fired = False
        self.chord_sequence = self.edge = self.expires = 0
        self.variant = 0
        self.pending = False

    def reset(self):
        self.neutral_seen = self.pending = False
        self.started = self.edge = self.expires = 0
        self.fired = False
        self.lb = self.circle = False

    def emit_intent(self, now, variant):
        self.chord_sequence += 1
        self.edge, self.expires = now, now + int(.4 * self.frequency)
        self.pending, self.variant = True, variant

    def process(self, event, now, context_valid=True):
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
        elif self.neutral_seen and not self.started:
            self.started = now
            self.neutral_seen = False
        self.lb, self.circle = lb, circle
        return dict(kind='logical_input', lb=lb, circle=circle, connected=self.connected,
                    context_valid=context_valid, gesture_started=self.started,
                    action='Leaping Slash' if self.variant else 'Charged Rush', chord_sequence=self.chord_sequence)

    def fields(self, now):
        if self.started and self.lb and self.circle and not self.fired and now-self.started >= self.threshold:
            self.emit_intent(now, 1)
            self.fired = True
        if now >= self.expires:
            self.pending = False
        return dict(heartbeat=now, edge=self.edge, expires=self.expires,
                    chord_sequence=self.chord_sequence, armed=self.pending,
                    held=self.lb and self.circle, latched=1, variant=self.variant)

    def dispatched(self, repeat=True):
        self.pending = False
