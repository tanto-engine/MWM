from nioh_native import Native
n=Native()
for r in [0x969940,0x969b56,0x76c2b8]: print(hex(r),n.function(r))
a=n.instructions(0x969940)
print('\n'.join(f'{x.address:x} {x.mnemonic} {x.op_str}' for x in a[:100]))
