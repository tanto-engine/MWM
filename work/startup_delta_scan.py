from nioh_native import Native
n=Native()
for lo,hi,needles in [(0x6fc000,0x720000,('[r','+ 0x28]')),(0x953000,0x956e00,('+ 0xf4]','+ 0x60]')),(0x968800,0x96b000,('+ 0x40]','+ 0x38]'))]:
 ins=list(n.cs.disasm(n.bytes(lo,hi-lo),lo))
 for j,i in enumerate(ins):
  if (lo==0x6fc000 and i.mnemonic=='addss' and '+ 0x24]' in i.op_str) or (lo!=0x6fc000 and any(s in i.op_str for s in needles)):
   print('CONTEXT',hex(i.address),'FUNC',hex(n.function(i.address)[0]))
   print('\n'.join(f'{x.address:x} {x.mnemonic} {x.op_str}' for x in ins[max(0,j-4):j+5]))
