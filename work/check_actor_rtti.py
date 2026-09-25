import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'outputs' / 'boss-probe'))
from boss_probe import LiveGame, U64

cfg = json.loads(Path('work/okatsu-discovery-2.json').read_text())
result = []
with LiveGame(cfg['pid']) as game:
    game.begin_sample()
    for candidate in cfg['candidates']:
        owner = int(candidate['owner_like'], 0)
        row = dict(object=candidate['object'], owner_like=hex(owner), owner_pointer_fields=[])
        try:
            raw = game.bytes(owner, 0x100)
            vt = U64(raw, 0)
            row['owner_rtti'] = game.rtti(vt) if game.base <= vt < game.base + game.main['size'] else None
            for offset in range(0, 0x100, 8):
                pointer = U64(raw, offset)
                if not 0x10000 <= pointer < 0x7FFFFFFFFFFF:
                    continue
                try:
                    child = game.bytes(pointer, 8)
                    vt = U64(child, 0)
                    if game.base <= vt < game.base + game.main['size']:
                        name = game.rtti(vt)
                        if name:
                            row['owner_pointer_fields'].append(dict(offset=hex(offset), pointer=hex(pointer), rtti=name))
                except OSError:
                    pass
        except OSError as e:
            row['error'] = str(e)
        result.append(row)
Path('work/okatsu-actor-rtti.json').write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
