import bisect, collections, json
from pathlib import Path
path=Path('runtime/sessions/20260925-003117/trace-1/events.jsonl')
events=[json.loads(line) for line in path.read_text().splitlines()]
player=hex(events[0]['config']['player'])
inputs=sorted((e for e in events if e['kind']=='input'),key=lambda e:(
    # Order saved input observations by completed polling time.
    # Select the QPC endpoint retained with each event.
    # Keep movement comparisons aligned with native action timestamps.
    e['poll_qpc_end']))
times=[e['poll_qpc_end'] for e in inputs]
rows=[]
keys={*range(3186,3190),*range(3247,3251),*range(3308,3312)}
for e in events:
    if e['kind']!='action_call' or e['actor']!=player or e['after_key'] not in keys:
        continue
    at=bisect.bisect_right(times,e['qpc'])-1
    if at<0: continue
    raw=inputs[at]
    rows.append(dict(key=e['after_key'],motion=e['motion_key'],input_key=e['input_key'],
                     qpc=e['qpc'],input_age_ms=(e['qpc']-raw['poll_qpc_end'])/10000,
                     buttons=raw['buttons'],axes=raw['axes'],native_result=e['native_result']))
table=json.loads(Path('work/allowed-state-resources.json').read_text())
evidence=dict(trace=str(path),player=player,records=rows,
              descriptors=[r for r in table['records'] if r['key'] in keys],
              note='Time-aligned input observations establish coincidence, not causation. No game writes.')
Path('work/guard-movement-evidence.json').write_text(json.dumps(evidence,indent=2))
print('counts',dict(collections.Counter((r['key'],r['motion']) for r in rows)))
for key in sorted({r['key'] for r in rows}):
    examples=[r for r in rows if r['key']==key and r['input_age_ms']<100 and r['buttons']&16]
    examples.sort(key=lambda r:(
        # Rank raw stick observations by distance from their neutral center.
        # Sum absolute deviations on the two movement axes.
        # Identify strong movement evidence without guessing its gameplay acceptance.
        abs(r['axes']['x']-32767)+abs(r['axes']['y']-32767)),reverse=True)
    print(key,examples[:2])
print('descriptor triples',[(r['key'],r['motion'],r['stance']) for r in evidence['descriptors']])
