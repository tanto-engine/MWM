# Read the active trace; no game memory writes or command publication.
import collections
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
status = json.loads((root / 'runtime/play-status.json').read_text())
path = Path(status['trace']) / 'events.jsonl'
events = []
for line in path.read_text().splitlines():
    try:
        events.append(json.loads(line))
    except json.JSONDecodeError:
        pass
session = next(e for e in events if e['kind'] == 'session')
player = hex(session['config']['player'])
calls = [e for e in events if e['kind'] == 'action_call' and e['actor'] == player]
moves = [e for e in calls if e['substitution_intended']]
pulses = [e for e in calls if e['input_key'] == 0xD5F]
windows = [e for e in events if e['kind'] == 'resource_state'
           and e.get('ki', {}).get('recoverable_target', 0) > 0
           and (e.get('source_clip_current') or e.get('leaping_clip_current'))]
report = dict(status=status, events=len(events),
              gestures=dict(collections.Counter(e['action'] for e in events if e['kind'] == 'gesture_intent')),
              moves=[dict(action=e.get('action_name'), exact=e['final_exact_match'],
                          reason=e['dispatch_reason'], qpc=e['qpc']) for e in moves],
              native_pulse_calls=[dict(before=hex(e['before_key']), after=hex(e['after_key']),
                                      result=e['native_result'], qpc=e['qpc']) for e in pulses],
              ki_window_samples=len(windows),
              ki_window_last=windows[-1] if windows else None,
              voice_suppressed=max((e.get('voice_suppressed_count', 0) for e in events), default=0))
print(json.dumps(report, indent=2))
