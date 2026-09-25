import json,struct
from pathlib import Path
from nioh_native import Native

n=Native()
out=Path(__file__).parent/'action-callers'
targets={0x7119c0,0x70ece0}
hits=[]
cache={}
blob=n.live_text
for i,b in enumerate(blob[:-4]):
    if b not in (0xe8,0xe9): continue
    at=n.live_text_rva+i
    dest=at+5+struct.unpack_from('<i',blob,i+1)[0]
    if dest not in targets: continue
    f=n.function(at)
    ins=cache.setdefault(f[0],n.instructions(at))
    match=next((x for x in ins if x.address==at and x.mnemonic in ('call','jmp')),None)
    if match is None: continue
    idx=ins.index(match)
    ctx=ins[max(0,idx-16):idx+5]
    hits.append({'at':hex(at),'target':hex(dest),'function':[hex(x) for x in f],'context':'\n'.join(f'{x.address:x} {x.mnemonic} {x.op_str}' for x in ctx)})
for f,ins in cache.items():
    (out/('snapshot-'+hex(f)+'.txt')).write_text('\n'.join(f'{x.address:x} {x.mnemonic} {x.op_str}' for x in ins))
(out/'snapshot-direct-callers.json').write_text(json.dumps(hits,indent=2))
print(json.dumps(hits,indent=2))
