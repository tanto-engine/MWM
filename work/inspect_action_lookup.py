import json
from pathlib import Path
import struct
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime'))
from boss_probe import LiveGame, U32

with LiveGame(12284) as game:
    game.begin_sample()
    header = game.bytes(game.base, 4096)
    pe = U32(header, 0x3c)
    count = struct.unpack_from('<H', header, pe + 6)[0]
    sections_at = pe + 24 + struct.unpack_from('<H', header, pe + 20)[0]
    pdata = next(struct.unpack_from('<II', header, sections_at + i * 40 + 8)
                 for i in range(count)
                 if header[sections_at + i * 40:sections_at + i * 40 + 8].rstrip(b'\0') == b'.pdata')
    functions = game.bytes(game.base + pdata[1], pdata[0])
    target = 0x73fa40
    begin, end, unwind = next(struct.unpack_from('<III', functions, at)
                              for at in range(0, len(functions) - 11, 12)
                              if U32(functions, at) <= target < U32(functions, at + 4))
    assert end - begin < 65536
    Path('work/action-lookup.bin').write_bytes(game.bytes(game.base + begin, end - begin))
    result = dict(function_rva=hex(begin), end_rva=hex(end), contexts=[])
    for address in (0x24390fbc910, 0x24390fbe390):
        raw, state = game.snapshot(address)
        result['contexts'].append(dict(object=hex(address), fields=state, object_bytes=raw.hex(),
                                       lookup_context_0x70_24_bytes=raw[0x70:0x88].hex()))
    Path('work/action-lookup-contexts.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
