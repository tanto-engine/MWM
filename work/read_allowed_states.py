import json, struct, sys
from pathlib import Path
sys.path.insert(0, str(Path('outputs/boss-probe').resolve()))
from boss_probe import LiveGame, U32, I32, U64
from action_banks import inspect_banks
p = json.loads(Path('outputs/okatsu-prototype/session-profile.json').read_text())
with LiveGame(p['session']['pid']) as game:
    assert game.identity == p['session']
    game.begin_sample()
    actor = int(p['player']['actor'], 0)
    raw, state = game.snapshot(actor)
    assert state['owner_like'] == p['player']['owner']
    banks = inspect_banks(game, actor)
    rows = []
    seen = set()
    for bank in banks['banks']:
        for entry in bank['records']:
            key = entry['key_u32']
            if not entry['enabled_byte'] or key in seen:
                continue
            seen.add(key)
            if not (key <= 60 or 3000 <= key <= 3350):
                continue
            body = game.bytes(int(entry['payload'], 0), 0x38)
            rows.append(dict(key=key, bank=bank['index'], stance=struct.unpack_from('<b',body,0xB)[0],
                             motion=I32(body,0x20), timing=I32(body,0x34),
                             prefix=body.hex(), descriptor=entry['descriptor'], payload=entry['payload']))
    assert [hex(U64(raw,0x70+i*8)) for i in range(3)] == p['player']['action_banks']
    after, end = game.snapshot(actor)
    assert state['owner_like'] == end['owner_like'] and raw[0x70:0x88] == after[0x70:0x88]
data = dict(session=p['session'], player=p['player']['actor'], owner=p['player']['owner'],
            action_banks=p['player']['action_banks'], records=rows, game_modified=False)
Path('work/allowed-state-resources.json').write_text(json.dumps(data,indent=2))
for row in rows:
    print(row['key'], row['bank'], row['stance'], row['motion'], row['prefix'][:40])
