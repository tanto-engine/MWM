"""Read-only check of the code-traced motion resource lookup."""
import json
from pathlib import Path
import struct
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'outputs/boss-probe'))
from boss_probe import LiveGame, U32, I32, U64

def motion_lookup(game, bank, key):
    header = game.bytes(bank, 0x488)
    pointers, lookup = U64(header, 0x468), U64(header, 0x480)
    table = game.bytes(lookup, 0x18)
    count, pairs = U32(table, 8), U64(table, 0x10)
    if not 0 < count <= 32768:
        raise ValueError('Implausible motion lookup count')
    raw = game.bytes(pairs, count*8)
    matches = [(i, I32(raw, i*8+4)) for i in range(count) if I32(raw, i*8) == key]
    answer = dict(bank=hex(bank), hash_slots=count, motion_key=key, matches=matches)
    if len(matches) == 1:
        index = matches[0][1]
        if not 0 <= index < 32768:
            raise ValueError('Implausible clip array index')
        pointer = U64(game.bytes(pointers+index*8, 8), 0)
        answer.update(index=index, clip=hex(pointer))
        if pointer:
            answer['clip_prefix'] = game.bytes(pointer, 0x40).hex()
    if game.bytes(lookup, 0x18) != table or game.bytes(bank+0x468, 0x20) != header[0x468:0x488]:
        raise ValueError('Motion lookup header changed')
    return answer

def inspect(game, actor, expected_owner):
    raw, before = game.snapshot(actor)
    owner = int(before['owner_like'], 0)
    if owner != expected_owner:
        raise ValueError('Actor owner changed')
    owned = game.bytes(owner, 0x78)
    motion = U64(owned, 0x38)
    timing = U64(owned, 0x68)
    body = game.bytes(motion, 0x108)
    row = dict(actor=hex(actor), owner=hex(owner), motion=hex(motion), motion_prefix=body.hex(),
               motion_selected_bank=I32(body, 0x48), motion_group=I32(body, 0x50),
               motion_current_clip=hex(U64(body, 0x58)), motion_current_key=I32(body, 0xec),
               timing=hex(timing), timing_prefix=game.bytes(timing, 0x80).hex(), banks=[])
    for slot in range(8):
        bank = U64(body, 8+slot*8)
        if bank:
            try:
                row['banks'].append(dict(slot=slot, **motion_lookup(game, bank, 1220)))
            except (OSError, ValueError) as error:
                row['banks'].append(dict(slot=slot, bank=hex(bank), error=str(error)))
    final, state = game.snapshot(actor)
    if state['owner_like'] != before['owner_like'] or game.bytes(owner+0x38, 8) != owned[0x38:0x40]:
        raise ValueError('Actor resource identity changed')
    return row

if __name__ == '__main__':
    with LiveGame(12284) as game:
        game.begin_sample()
        data = dict(session=game.identity, actors=[inspect(game, 0x24390fbc910, 0x24380087dc0),
                                                  inspect(game, 0x24390fbe390, 0x2438008f7a0)])
    Path('work/okatsu-motion-banks.json').write_text(json.dumps(data, indent=2))
    print(json.dumps(data, indent=2))
