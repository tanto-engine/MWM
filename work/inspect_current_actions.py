import json, struct, sys
from pathlib import Path
sys.path.insert(0, str(Path('runtime').resolve()))
from boss_probe import LiveGame, metadata
from action_banks import inspect_banks, resolve
from motion_resources import motion_lookup
from timing_resources import lookup
p = json.loads(Path('runtime/session-profile.json').read_text())
with LiveGame(p['session']['pid']) as g:
    if g.identity != p['session']: raise ValueError('Session changed')
    banks = inspect_banks(g, int(p['source']['actor'], 0))
    rows = []
    for key in range(0xC50, 0xC71):
        e = resolve(banks, key)
        if not e: continue
        body = g.bytes(int(e['payload'],0), 0xB0)
        row = dict(key=hex(key), entry=e, payload=body.hex(),
                   motion=struct.unpack_from('<i',body,0x20)[0],
                   metadata=metadata(g,int(e['descriptor'],0),64))
        rows.append(row)
    Path('work/okatsu-current-actions.json').write_text(json.dumps(dict(session=g.identity,rows=rows),indent=2))
    print([(r['key'],r['motion'], sorted(set(e.get('target_key_0x14_i16',-1) for e in r['metadata']['transition_entries']))) for r in rows])
