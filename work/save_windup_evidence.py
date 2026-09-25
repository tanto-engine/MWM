from nioh_native import Native
from pathlib import Path
import json,struct
n=Native()
ranges=[(0x7190fe,0x71911f),(0x747694,0x7476ca),(0x6ff8f1,0x6ff951),(0x955a40,0x955a97),(0x9694c0,0x969546),(0x9683a0,0x9683e4),(0x9684c9,0x9684da),(0x969b50,0x969b66),(0x718cfa,0x718d29)]
lines=['Native startup speed evidence (offline saved exact-build text).', 'C64 only: preserve all event traversal; no animation/event cursor seek.', 'actor+6A8 speed and+24 effective delta are scaled together after native719050.', 'Boost boundary30 is a tuning choice, not a proved first-damage frame.']
for lo,hi in ranges:
 lines.append(f'\nRVA {lo:X}..{hi:X}')
 for start,end,_ in n.functions:
  if start<hi and end>lo:
   for i in n.cs.disasm(n.bytes(start,end-start),start):
    if lo<=i.address<hi: lines.append(f'{i.address:08X} {i.mnemonic:8} {i.op_str}')
Path('work/rush-windup-clock-evidence.txt').write_text('\n'.join(lines))
print(json.dumps({'clip_native_frame_rate_multiplier':struct.unpack('<f',n.bytes(0x954f78+8+0xc33b6c,4))[0],'evidence':'work/rush-windup-clock-evidence.txt'}))
