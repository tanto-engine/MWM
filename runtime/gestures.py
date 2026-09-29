# Recognize configured sword gestures using saved controller identities.
import math
from move_imports import IMPORT_LIMIT

SEQUENCE_WINDOW_SECONDS = .6


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
                    latched=0 if self.variant == self.string_variant else 1, variant=self.variant,
                    reserve=self.variant != self.string_variant and not (self.fired and not self.pending))

    def dispatched(self, repeat=True):
        # Consume the pending gesture after native acceptance.
        # Clear its armed state while retaining the physical hold information.
        # A single press cannot repeatedly enqueue the same move.
        self.pending = False


class SequenceGesture:
    """Recognize modifier + first press, release, then a separate follow-up press."""
    def __init__(self, calibration, binding, frequency):
        if binding['device'] != calibration['device'] or binding['lb_mask'] != calibration['lb_mask']:
            raise ValueError('Binding does not match the saved controller')
        self.device = calibration['device']
        self.modifier, self.first, self.followup = (binding[key] for key in
            ('modifier_mask','trigger_mask','followup_mask'))
        if len({self.modifier,self.first,self.followup})!=3 or any(
                type(bit) is not int or not 0<bit<=0x80000000 or bit&(bit-1)
                for bit in (self.modifier,self.first,self.followup)):
            raise ValueError('Sequence controls must be distinct single buttons')
        self.variant=binding['variant']
        if type(self.variant) is not int or not 0<=self.variant<IMPORT_LIMIT or frequency<=0:
            raise ValueError('Invalid sequence binding')
        self.frequency=frequency
        self.window=int(SEQUENCE_WINDOW_SECONDS*frequency)
        self.connected=False
        self.chord_sequence=0
        self.reset()

    def reset(self):
        self.ready=self.pending=False
        self.stage=self.started=self.deadline=self.edge=self.expires=0
        self.previous=(False,False,False)

    def process(self, event, now, context_valid=True):
        if not context_valid:
            self.reset()
        if (event.get('backend'),event.get('slot'))!=(self.device['backend'],self.device['slot']):
            return None
        if event['kind']=='input_device':
            self.reset()
            self.connected=identity(event)==self.device
            return dict(kind='device_match',accepted=self.connected)
        if event['kind']=='input_unavailable':
            self.connected=False
            self.reset()
            return dict(kind='device_unavailable')
        if event['kind']!='input':
            return None
        buttons=event.get('buttons')
        if (not self.connected or not context_valid or type(buttons) is not int
                or not 0<=buttons<=0xffffffff or buttons&~(self.modifier|self.first|self.followup)):
            self.reset()
            return None
        if event.get('edge_basis')=='unknown':
            self.reset()
        modifier,first,followup=(bool(buttons&bit) for bit in (self.modifier,self.first,self.followup))
        _,previous_first,previous_followup=self.previous
        if not modifier:
            self.stage=self.started=self.deadline=0
            self.pending=False
            self.ready=not first and not followup
        elif self.pending:
            pass
        elif self.stage==1:
            if followup:
                self.stage=self.started=0
                self.ready=False
            elif not first:
                self.stage=2
                self.deadline=now+self.window
        elif self.stage==2:
            if now>self.deadline or first:
                self.stage=self.started=0
                self.ready=not first and not followup
            elif followup and not previous_followup:
                self.chord_sequence+=1
                self.edge,self.expires=now,now+int(.4*self.frequency)
                self.pending=True
                self.stage=self.started=0
                self.ready=False
        elif not first and not followup:
            self.ready=True
        elif first and not previous_first and not followup and self.ready:
            self.stage,self.started=1,now
            self.ready=False
        else:
            self.ready=False
        self.previous=(modifier,first,followup)
        return dict(kind='logical_input',connected=self.connected,
                    gesture_started=self.started,chord_sequence=self.chord_sequence)

    def fields(self, now):
        if self.stage==2 and now>self.deadline:
            self.stage=self.started=0
        if now>=self.expires:
            self.pending=False
        return dict(heartbeat=now,edge=self.edge,expires=self.expires,
                    chord_sequence=self.chord_sequence,armed=self.pending,
                    held=self.previous[0],latched=1,variant=self.variant,reserve=False)

    def dispatched(self, repeat=True):
        self.pending=False


class RoutedGesture:
    """Select one validated physical chord and stance for the existing command slot."""
    def __init__(self, calibration, binding, frequency, string_variant=None):
        groups={}
        sequences={}
        for route in binding['routes']:
            stances=range(3) if route['stance']=='any' else [('high','mid','low').index(route['stance'])]
            for stance in stances:
                if route['gesture']=='sequence':
                    key=(stance,route['modifier_mask'],route['trigger_mask'],route['followup_mask'])
                    sequences[key]=route['variant']
                    continue
                key=(stance,route['modifier_mask'],route['trigger_mask'])
                variants=groups.setdefault(key,[None,None])
                variants[('tap','hold').index(route['gesture'])]=route['variant']
        self.gates={key:ControllerGesture(calibration,dict(binding,modifier_mask=key[1],trigger_mask=key[2],
                            variants=variants,string_enabled=False),frequency) for key,variants in groups.items()}
        self.sequence_keys=set(sequences)
        self.gates.update({key:SequenceGesture(calibration,dict(binding,modifier_mask=key[1],trigger_mask=key[2],
                            followup_mask=key[3],variant=variant),frequency) for key,variant in sequences.items()})
        self.string=ControllerGesture(calibration,dict(binding,variants=[None,None]),frequency,string_variant)
        self.seen={key:0 for key in self.gates}
        self.seen['string']=0
        self.stance=self.active=None
        self.chord_sequence=self.variant=0
        self.connected=False

    def reset(self):
        for gate in (*self.gates.values(),self.string): gate.reset()
        for key,gate in self.gates.items(): self.seen[key]=gate.chord_sequence
        self.seen['string']=self.string.chord_sequence
        self.active=None

    def set_stance(self, stance):
        if stance not in (0,1,2):
            self.reset()
            self.stance=None
        elif stance!=self.stance:
            self.reset()
            self.stance=stance

    def process(self, event, now, context_valid=True):
        if not context_valid or event.get('kind') in ('input_device','input_unavailable') or event.get('edge_basis')=='unknown':
            self.reset()
        result=self.string.process(event,now,context_valid)
        candidate='string' if self.string.string_held or self.string.pending else None
        if candidate=='string':
            for key,gate in self.gates.items():
                gate.reset();self.seen[key]=gate.chord_sequence
        else:
            sequence_candidate=None
            for key,gate in self.gates.items():
                if event.get('kind')!='input' or key[0]==self.stance:
                    observed=gate.process(event,now,context_valid)
                    if key in self.sequence_keys and key[0]==self.stance and (gate.started or gate.pending or gate.chord_sequence>self.seen[key]):
                        sequence_candidate=key
                        result=observed
                    elif key not in self.sequence_keys and key[0]==self.stance and (gate.started or gate.chord_sequence>self.seen[key]):
                        candidate=key
                        result=observed
            if sequence_candidate is not None:
                candidate=sequence_candidate
                for key,gate in self.gates.items():
                    if key!=candidate:
                        gate.reset();self.seen[key]=gate.chord_sequence
                self.string.reset()
        if candidate is not None and candidate!=self.active:
            if self.active is not None: self._gate(self.active).dispatched()
            self.active=candidate
        if self.active is not None:
            gate=self._gate(self.active)
            if gate.chord_sequence>self.seen[self.active]:
                self.chord_sequence+=1
                self.seen[self.active]=gate.chord_sequence
            self.variant=gate.variant
            if result and result.get('kind')=='logical_input': result=dict(result,chord_sequence=self.chord_sequence)
        self.connected=self.string.connected
        return result

    def _gate(self, key):
        return self.string if key=='string' else self.gates[key]

    def fields(self, now):
        if self.active is None:
            return dict(heartbeat=now,edge=0,expires=0,chord_sequence=self.chord_sequence,
                        armed=False,held=False,latched=0,variant=0,reserve=False,chord_policy=0)
        gate=self._gate(self.active)
        fields=gate.fields(now)
        if gate.chord_sequence>self.seen[self.active]:
            self.chord_sequence+=1
            self.seen[self.active]=gate.chord_sequence
        self.variant=fields['variant']
        policy=0 if self.active=='string' else (1<<(34-self.active[0])) | (
            1<<35 if self.active in self.sequence_keys else (self.active[1]|self.active[2])<<16)
        fields.update(chord_sequence=self.chord_sequence,chord_policy=policy,
                      reserve=self.active!='string' and (gate.pending if self.active in self.sequence_keys else
                               bool(gate.started and not gate.fired) or gate.pending))
        return fields

    def dispatched(self, repeat=True):
        if self.active is not None: self._gate(self.active).dispatched()
