from nioh_native import Native
n=Native()
for lo,hi in [(0x969470,0x969547),(0x76d840,0x76da50),(0x747650,0x747d00)]:
 for start,end,_ in n.functions:
  if start<hi and end>lo:
   ins=list(n.cs.disasm(n.bytes(start,end-start),start))
   if lo==0x747650:
    for j,i in enumerate(ins):
     if i.mnemonic=='call' and any(x in i.op_str for x in ['0x90]','0x38]','0x40]','0x60]']):
      print('\n'.join(f'{x.address:x} {x.mnemonic} {x.op_str}' for x in ins[max(0,j-7):j+3]))
   else: print('\n'.join(f'{x.address:x} {x.mnemonic} {x.op_str}' for x in ins if lo<=x.address<hi))
