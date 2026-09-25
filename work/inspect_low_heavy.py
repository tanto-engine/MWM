import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path('outputs/boss-probe').resolve()))
from boss_probe import LiveGame, metadata
from action_banks import inspect_banks, resolve

scan = json.loads(Path('work/jin-player-scan.json').read_text())
players = []
with LiveGame(scan['pid']) as game:
    assert game.identity['creation_filetime'] == scan['creation_filetime']
    for candidate in scan['candidates']:
        if int(candidate['owner_like'], 0) < 0x10000:
            continue
        try:
            banks = inspect_banks(game, int(candidate['object'], 0))
        except (OSError, ValueError) as error:
            print('Discarded scan candidate', candidate['object'], str(error))
            continue
        fingerprint = resolve(banks, 0xC64)
        if fingerprint is None:
            continue
        if struct.unpack('<i', game.bytes(int(fingerprint['payload'], 0) + 0x20, 4))[0] == 2033:
            players.append((candidate, banks))
    assert len(players) == 1, len(players)
    player, banks = players[0]
    rows = []
    for key in range(3276, 3445):
        entry = resolve(banks, key)
        if entry is not None:
            row = metadata(game, int(entry['descriptor'], 0), 128)
            rows.append(row)
            payload = row['payload_prefix']
            raw = bytes.fromhex(payload['bytes'])
            print(hex(key), payload['motion_id'], 'stance', raw[11], 'recover', struct.unpack_from('<h',raw,36)[0], 'rows', row['transition_slice']['count'])
    Path('work/player-low-heavy-evidence.json').write_text(json.dumps(dict(session=game.identity, player=player, banks=banks, actions=rows), indent=2))
