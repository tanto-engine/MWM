from nioh_native import Native
from pathlib import Path
import struct

n = Native()
text = n.live_text
base = n.live_text_rva
targets = {0x719050, 0x751ec0, 0x747440, 0x747550}
direct = []
at = text.find(b'\xe8')
while at >= 0 and at + 5 <= len(text):
    dest = base + at + 5 + struct.unpack_from('<i', text, at + 1)[0]
    if dest in targets:
        direct.append((base + at, dest))
    at = text.find(b'\xe8', at + 1)
out = ['DIRECT: ' + repr([(hex(a), hex(b)) for a,b in direct]), n.text(0x719050), n.text(0x751ec0)]
for call, dest in direct:
    ins = n.instructions(call)
    for j, i in enumerate(ins):
        if i.address == call and i.mnemonic == 'call':
            out.append('\nDIRECT CALL CONTEXT '+hex(call))
            out.extend(f'{x.address:08x} {x.mnemonic:8} {x.op_str}' for x in ins[max(0,j-14):j+9])

hits = set()
for reg in range(8):
    needle = bytes([0xff, 0x50+reg, 0x30])
    at = text.find(needle)
    while at >= 0:
        hits.add(base+at)
        at = text.find(needle,at+1)
functions = {n.function(a)[0] for a in hits}
for start in sorted(functions):
    ins = n.instructions(start)
    for j,i in enumerate(ins):
        if i.mnemonic == 'call' and ' + 0x30]' in i.op_str and i.address in hits:
            window = ins[max(0,j-10):j+6]
            if any('xmm1' in x.op_str for x in window[:11]):
                out.append('\nVIRTUAL FLOAT CALL '+hex(i.address)+' FUNCTION '+hex(start))
                out.extend(f'{x.address:08x} {x.mnemonic:8} {x.op_str}' for x in window)
out.append('\nVTABLE '+repr([(hex(i*8),hex(v)) for i,v in enumerate(n.vtable(0x11a3530,12))]))
Path('work/tick-call-evidence.txt').write_text('\n'.join(out))
print('direct',direct,'virtual candidates',len(hits),'output lines',len('\n'.join(out).splitlines()))
