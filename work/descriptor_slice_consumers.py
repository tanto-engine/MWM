from pathlib import Path
import json
import re
from nioh_native import Native
n = Native()
n.cs.skipdata = True
rows = []
out = Path(__file__).parent/'descriptor-layout'
pattern = re.compile(r'\[(?!rsp|rbp)[a-z0-9]+ \+ 0x(48|58|68|78|88|98|a8|b8|52|62|72|82|92|a2|b2|c2)\]')
for at, size, mnemonic, operands in n.cs.disasm_lite(n.bytes(0x6f0000,0x61000),0x6f0000):
    match = pattern.search(operands)
    if match and (mnemonic == 'lea' or 'word ptr' in operands and 'dword ptr' not in operands and 'qword ptr' not in operands):
        fn = n.function(at)[0]
        rows.append(dict(address=hex(at), function=hex(fn), instruction=f'{mnemonic} {operands}'))
        (out/f'{fn:08x}.txt').write_text(n.text(fn))
(out/'slice-consumers.json').write_text(json.dumps(rows,indent=2))
print(json.dumps(rows,indent=2))
