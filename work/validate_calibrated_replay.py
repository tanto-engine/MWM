import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'outputs/okatsu-prototype'))
from calibrate_controller import CalibratedChord

mapper = CalibratedChord(json.loads(Path('outputs/okatsu-prototype/controller-calibration.json').read_text()))
events = [json.loads(x) for x in Path('work/controller-calibration-v3/raw-events.jsonl').read_text().splitlines()]
fired=[]
for event in events:
    logical=mapper.process(event,context_valid=True)
    if logical and logical.get('chord_candidate'):
        fired.append(dict(phase=event['phase'],observed_monotonic=logical['observed_monotonic'],lb=logical['lb'],lt=logical['lt']))
assert len(fired)==1 and fired[0]['phase']=='both', fired
print(json.dumps(dict(replay_chords=fired, game_modified=False)))
