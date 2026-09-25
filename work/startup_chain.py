from nioh_native import Native
import struct,json
n=Native()
for target in [0x955a40,0x969510,0x969a30]:
 print('TARGET',hex(target))
 b=n.live_text
 for at in range(len(b)-5):
  if b[at]==0xe8 and n.live_text_rva+at+5+struct.unpack_from('<i',b,at+1)[0]==target:
   r=n.live_text_rva+at
   ins=n.instructions(r); j=next((i for i,x in enumerate(ins) if x.address==r),0)
   print('CALL',hex(r),'FUNC',hex(n.function(r)[0]))
   print('\n'.join(f'{x.address:x} {x.mnemonic} {x.op_str}' for x in ins[max(0,j-9):j+5]))
print('ACTION 28 ADVANCE')
for start,end,_ in n.functions:
 if 0x6fc000<=start<0x720000:
  ins=list(n.cs.disasm(n.bytes(start,end-start),start))
  for j,i in enumerate(ins):
   if i.mnemonic=='movss' and i.op_str.startswith('dword ptr [') and '+ 0x28], xmm' in i.op_str:
    print('\n'.join(f'{x.address:x} {x.mnemonic} {x.op_str}' for x in ins[max(0,j-7):j+3]))
print('AUDIO EVENTS')
for x in json.load(open('work/okatsu-audio-metadata.json')): print(x['name'], x['events'])
