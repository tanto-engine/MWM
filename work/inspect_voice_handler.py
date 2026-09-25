from nioh_native import Native
from pathlib import Path
import struct
n=Native(); data=n.live_text; base=n.live_text_rva
hits=[]; pos=data.find(b'\xe8')
while pos>=0 and pos+5<=len(data):
    target=base+pos+5+struct.unpack_from('<i',data,pos+1)[0]
    if target in (0x9670a0,0x967890): hits.append((base+pos,target))
    pos=data.find(b'\xe8',pos+1)
out=[]
for address,target in hits:
    ins=n.instructions(address)
    for at,item in enumerate(ins):
        if item.address==address and item.mnemonic=='call':
            out.append(f'CALL {address:#x} -> {target:#x}, FUNCTION {n.function(address)[0]:#x}')
            out.extend(f'{i.address:08x} {i.mnemonic:8} {i.op_str}' for i in ins[max(0,at-14):at+7])
needle=struct.pack('<Q',n.base+0x9670a0)
refs=[]
for name,size,rva,rawsize,raw in n.sections:
    if name!='.rdata': continue
    buf=n.bytes(rva,rawsize); at=buf.find(needle)
    while at>=0: refs.append(rva+at); at=buf.find(needle,at+1)
out.append('RDATA_REFS '+repr([hex(x) for x in refs]))
Path('work/voice-handler-evidence.txt').write_text('\n'.join(out));print('\n'.join(out))
