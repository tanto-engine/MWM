import json
from pathlib import Path
from nioh_native import Native

native = Native()
methods = native.vtable(0x11a3530, 100)
out = Path('work/action-methods')
out.mkdir(exist_ok=True)
index = []
for slot, rva in enumerate(methods):
    if not 0x1000 <= rva < 0x119b000:
        break
    start, end, unwind = native.function(rva)
    text = native.text(rva)
    (out / f'{slot*8:03x}-{rva:x}.txt').write_text(text)
    index.append(dict(slot=hex(slot*8), rva=hex(rva), size=end-start,
                      references_current=' + 0x58]' in text,
                      references_bank=' + 0x68]' in text,
                      references_payload_selector=' + 0x20]' in text))
(out / 'index.json').write_text(json.dumps(index, indent=2))
print(json.dumps(index, indent=2))
