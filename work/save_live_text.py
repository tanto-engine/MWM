# Read-only bounded snapshot of the loaded executable code for offline analysis.
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'outputs/boss-probe'))
from boss_probe import LiveGame
from nioh_native import Native

native = Native()
section = next(s for s in native.sections if s[0] == '.text')
with LiveGame(12284) as game:
    game.begin_sample()
    code = bytearray()
    for offset in range(0, section[1], 1024*1024):
        code += game.bytes(game.base + section[2] + offset, min(1024*1024, section[1]-offset))
    assert code[0x7119c0-section[2]:0x7119c5-section[2]] == bytes.fromhex('48895c2408')
    Path('work/live-text.bin').write_bytes(code)
    Path('work/live-text-identity.json').write_text(json.dumps(dict(**game.identity, rva=section[2], size=len(code)), indent=2))
    print(json.dumps(dict(pid=game.pid, rva=hex(section[2]), bytes_read=len(code), game_modified=False)))
