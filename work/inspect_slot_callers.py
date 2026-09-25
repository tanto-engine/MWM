import json,struct
from pathlib import Path
from nioh_native import Native
from capstone.x86_const import X86_OP_MEM
n=Native()
out=Path(__file__).parent/'action-callers'
blob=n.live_text
candidates=set()
pos=0
while True:
    pos=blob.find(b'\xa0\x01\x00\x00',pos)
    if pos<0: break
    f=n.function(n.live_text_rva+pos)
    candidates.add(f)
    pos+=4
hits=[]
for f in sorted(candidates):
    ins=n.instructions(f[0])
    matching=[]
    for i,x in enumerate(ins):
        if x.mnemonic not in ('call','jmp'): continue
        if not any(o.type==X86_OP_MEM and o.mem.disp==0x1a0 for o in x.operands): continue
        ctx=ins[max(0,i-18):i+4]
        hits.append({'at':hex(x.address),'function':[hex(a) for a in f],'context':'\n'.join(f'{a.address:x} {a.mnemonic} {a.op_str}' for a in ctx)})
        matching.append(x)
    if matching:
        (out/('slot-'+hex(f[0])+'.txt')).write_text('\n'.join(f'{x.address:x} {x.mnemonic} {x.op_str}' for x in ins))
(out/'snapshot-slot-callers.json').write_text(json.dumps(hits,indent=2))
print(json.dumps(hits,indent=2))
