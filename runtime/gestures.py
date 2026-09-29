# Recognize configured sword gestures using saved controller identities.
import math
from move_imports import IMPORT_LIMIT

SEQUENCE_WINDOW_SECONDS = .6
ATTACK_WINDOW_SECONDS = .6
ATTACK_SOURCES = {
    'after_quick': ((0xCB3, 3100), (0xC76, 2100), (0xCF0, 4100)),
    'after_strong': ((0xCB7, 3300), (0xC7A, 2300), (0xCF5, 4300)),
}
ATTACK_KEYS = frozenset(key for sources in ATTACK_SOURCES.values() for key,_ in sources)


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

    def reset(self):
        # Discard gesture state after a discontinuity or invalid context.
        # Clear press timing, pending intent and both neutral-observation latches.
        # A held button cannot carry an old press across reconnection.
        self.neutral_seen = self.pending = False
        self.started = self.edge = self.expires = 0
        self.fired = False
        self.lb = self.circle = False

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
        # Gate identity and context, then track chord edges.
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
                    held=self.lb and self.circle,
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


class AttackFollowupGesture:
    """Accept a fresh Guard chord shortly after a confirmed sword opener."""
    def __init__(self, calibration, binding, frequency):
        if binding['device'] != calibration['device'] or binding['lb_mask'] != calibration['lb_mask']:
            raise ValueError('Binding does not match the saved controller')
        self.device = calibration['device']
        self.modifier, self.trigger = binding['modifier_mask'], binding['trigger_mask']
        self.gesture, self.variant = binding['gesture'], binding['variant']
        if self.gesture not in ATTACK_SOURCES or frequency <= 0 or type(self.variant) is not int or not 0 <= self.variant < IMPORT_LIMIT:
            raise ValueError('Invalid attack follow-up binding')
        self.frequency = frequency
        self.window = int(ATTACK_WINDOW_SECONDS * frequency)
        self.source_button = 0x8000 if self.gesture == 'after_strong' else 0x4000
        self.connected = False
        self.chord_sequence = 0
        self.reset()

    def reset(self):
        self.ready = self.pending = False
        self.deadline = self.edge = self.expires = 0
        self.source = self.recovery = self.tracking_deadline = 0
        self.previous = 0

    def confirm(self, now, descriptor, recovery):
        if self.connected and descriptor >= 0x10000 and recovery > 0:
            self.source, self.recovery = descriptor, recovery
            self.tracking_deadline = now + 3 * self.frequency
            self.deadline = 0
            self.ready = self.pending = False

    def advance(self, now, descriptor, frame):
        if not self.source:
            return
        if now > self.tracking_deadline or not math.isfinite(frame) or (descriptor != self.source and not self.deadline):
            self.reset()
        elif not self.deadline and frame >= self.recovery:
            self.deadline = now + self.window
            self.ready = False

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
        if (not self.connected or not context_valid or type(buttons) is not int
                or not 0 <= buttons <= 0xffffffff or event.get('edge_basis') == 'unknown'):
            self.reset()
            return None
        if (self.deadline and now > self.deadline) or buttons & ~(self.modifier | self.trigger | self.source_button):
            self.reset()
        elif self.deadline and not self.pending:
            if buttons & self.source_button:
                self.ready = False
            elif not buttons & self.trigger:
                self.ready = True
            elif (self.ready and buttons == self.modifier | self.trigger
                    and not self.previous & self.trigger):
                self.chord_sequence += 1
                self.edge, self.expires = now, now + int(.4 * self.frequency)
                self.pending = True
                self.ready = False
                self.deadline = 0
                self.source = 0
        self.previous = buttons
        return dict(kind='logical_input', connected=self.connected,
                    chord_sequence=self.chord_sequence)

    def fields(self, now):
        if now >= self.expires:
            self.pending = False
        return dict(heartbeat=now, edge=self.edge, expires=self.expires,
                    chord_sequence=self.chord_sequence, armed=self.pending,
                    held=False, latched=1, variant=self.variant, reserve=self.pending)

    def dispatched(self, repeat=True):
        self.pending = False


class RoutedGesture:
    """Select one validated physical chord and stance for the existing command slot."""
    def __init__(self, calibration, binding, frequency, string_variant=None):
        groups={}
        sequences={}
        attacks={}
        for route in binding['routes']:
            stances=range(3) if route['stance']=='any' else [('high','mid','low').index(route['stance'])]
            for stance in stances:
                if route['gesture'] in ATTACK_SOURCES:
                    attacks[stance,route['modifier_mask'],route['trigger_mask'],route['gesture']]=route['variant']
                    continue
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
        self.attack_keys=set(attacks)
        self.gates.update({key:SequenceGesture(calibration,dict(binding,modifier_mask=key[1],trigger_mask=key[2],
                            followup_mask=key[3],variant=variant),frequency) for key,variant in sequences.items()})
        self.gates.update({key:AttackFollowupGesture(calibration,dict(binding,modifier_mask=key[1],trigger_mask=key[2],
                            gesture=key[3],variant=variant),frequency) for key,variant in attacks.items()})
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

    def observe_action(self, record, player, now, recovery):
        if (record.get('actor') != hex(player) or record.get('native_result') != 1
                or record.get('valid_fields',0) & 20 != 20
                or record['valid_fields'] & ((1 << 16) | (1 << 18))
                or record.get('input_key') != record.get('after_key')
                or not 0 <= now - record.get('qpc', -1) <= self.string.frequency // 10
                or self.stance not in (0,1,2)):
            return
        for key in self.attack_keys:
            if key[0] == self.stance and (record['after_key'],record['motion_key']) == ATTACK_SOURCES[key[3]][self.stance]:
                self.gates[key].confirm(record['qpc'], int(record['after'],16), recovery)

    def advance_attack(self, now, descriptor, frame):
        for key in self.attack_keys:
            self.gates[key].advance(now, descriptor, frame)

    @property
    def attack_watch(self):
        return any(self.gates[key].source for key in self.attack_keys)

    def process(self, event, now, context_valid=True):
        if not context_valid or event.get('kind') in ('input_device','input_unavailable') or event.get('edge_basis')=='unknown':
            self.reset()
        result=self.string.process(event,now,context_valid)
        candidate='string' if self.string.pending else None
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
                    elif key in self.attack_keys and key[0]==self.stance and (gate.pending or gate.chord_sequence>self.seen[key]):
                        sequence_candidate=key
                        result=observed
                    elif key not in self.sequence_keys and key not in self.attack_keys and key[0]==self.stance and (gate.started or gate.chord_sequence>self.seen[key]):
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
        if self.string.string_variant is not None and gate.variant==self.string.string_variant and fields['held']:
            fields['latched']=0
        if gate.chord_sequence>self.seen[self.active]:
            self.chord_sequence+=1
            self.seen[self.active]=gate.chord_sequence
        self.variant=fields['variant']
        policy=0 if self.active=='string' else (1<<(34-self.active[0])) | (
            (1 << (36 if self.active[3]=='after_strong' else 37)) if self.active in self.attack_keys else
            1<<35 if self.active in self.sequence_keys else (self.active[1]|self.active[2])<<16)
        fields.update(chord_sequence=self.chord_sequence,chord_policy=policy,
                      reserve=self.active!='string' and (gate.pending if self.active in self.sequence_keys or self.active in self.attack_keys else
                               bool(gate.started and not gate.fired) or gate.pending))
        return fields

    def dispatched(self, repeat=True):
        if self.active is not None: self._gate(self.active).dispatched()
