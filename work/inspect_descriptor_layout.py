"""Offline candidate discovery for the native 0xD0 action-record layout."""
from pathlib import Path
import json
from nioh_native import Native

n = Native()
data, base = n.live_text, n.live_text_rva
functions = set()
at = data.find(bytes.fromhex('d0 00 00 00'))
while at >= 0:
    functions.add(n.function(base + at)[0])
    at = data.find(bytes.fromhex('d0 00 00 00'), at + 1)
out = Path(__file__).parent / 'descriptor-layout'
out.mkdir(exist_ok=True)
rows = []
for fn in sorted(functions):
    try:
        ins = n.instructions(fn)
    except ValueError:
        continue
    matches = [i for i in ins if i.mnemonic in ('imul', 'mov', 'add', 'sub', 'cmp')
               and i.op_str.endswith(', 0xd0')]
    if matches:
        text = '\n'.join(f'{i.address:08x} {i.mnemonic:8} {i.op_str}' for i in ins)
        (out / f'{fn:08x}.txt').write_text(text)
        rows.append(dict(function=hex(fn), matches=[f'{i.address:x}: {i.mnemonic} {i.op_str}' for i in matches]))
(out / 'index.json').write_text(json.dumps(rows, indent=2))
print(json.dumps(rows, indent=2))
