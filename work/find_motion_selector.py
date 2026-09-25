from nioh_native import Native
from collections import deque
from pathlib import Path

n = Native()
history = deque(maxlen=18)
found = []
for address, size, name, operands in n.cs.disasm_lite(n.bytes(0x6f0000, 0x70000), 0x6f0000):
    line = f'{address:08x} {name:8} {operands}'
    history.append(line)
    if 'dword ptr [' in operands and '+ 0x20]' in operands and any('+ 0x58]' in x for x in history):
        found.append('\n'.join(history))
Path('work/motion-selector-candidates.txt').write_text('\n\n'.join(found))
print(f'{len(found)} candidate sequences')
