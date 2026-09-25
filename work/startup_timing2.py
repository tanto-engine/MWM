from nioh_native import Native
import struct
n=Native()
for start,end,_ in n.functions:
 if 0x969830<=start<0x969900:
  print(n.text(start))
print('SPEED POINTER READS')
for start,end,_ in n.functions:
 if 0x968000<=start<0x969bd5:
  a=list(n.cs.disasm(n.bytes(start,end-start),start))
  for j,i in enumerate(a):
   if (i.mnemonic=='mulss' or i.mnemonic=='movss') and ('+ 0xf4]' in i.op_str or '+ 0x6a8]' in i.op_str or '+ 0x24]' in i.op_str):
    print('\n'.join(f'{x.address:x} {x.mnemonic} {x.op_str}' for x in a[max(0,j-6):j+5]))
