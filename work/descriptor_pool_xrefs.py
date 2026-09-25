from pathlib import Path
import json
import re
import struct
from nioh_native import Native
n = Native()
targets = {}
targets[0x18717D0] = 'pool selector receiving address 0x1871888 at RVA734C72'
for i in n.instructions(0x734910):
    if 0x734bcd <= i.address <= 0x734c25:
        for op in i.operands:
            if op.type == 3 and n.cs.reg_name(op.mem.base) == 'rip':
                targets[i.address + i.size + op.mem.disp] = f'{i.address:x} {i.mnemonic} {i.op_str}'
print('targets', json.dumps({hex(k):v for k,v in targets.items()}))
matches = []
for m in re.finditer(rb'[\x48-\x4f][\x8b\x8d\x89][\x05\x0d\x15\x1d\x25\x2d\x35\x3d]', n.live_text):
    at = m.start()
    target = n.live_text_rva + at + 7 + struct.unpack_from('<i',n.live_text,at+3)[0]
    if target in targets:
        rva = n.live_text_rva + at
        fn = n.function(rva)[0]
        matches.append(dict(rva=hex(rva), function=hex(fn), target=hex(target)))
        (Path(__file__).parent/'descriptor-layout'/f'{fn:08x}.txt').write_text(n.text(fn))
print(json.dumps(matches, indent=2))
