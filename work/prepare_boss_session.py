"""Generate the current-session preview constants from a revalidated read-only profile."""
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'outputs/boss-probe'))
from boss_probe import LiveGame, U64, U32, I32


def main():
    p = json.loads((ROOT / 'work/okatsu-resource-profile-3b.json').read_text())
    source, player = p['source'], p['player']
    sm = next(b for b in source['resources']['motion']['banks'] if b['slot'] == 0)
    st = next(b for b in source['resources']['timing']['banks'] if b['slot'] == 0)
    def pointer_slots(actor, kind, slots, field):
        rows = actor['resources'][kind]['banks']
        return [int(next(r for r in rows if r['slot'] == slot)[field], 0) for slot in slots]
    fields = dict(
        player=int(player['actor'], 0), player_owner=int(player['owner'], 0),
        source_actor=int(source['actor'], 0), source_owner=int(source['owner'], 0),
        vtable=int(p['session']['vtable'], 0),
        source_bank=int(source['action_resolution']['bank_address'], 0),
        source_descriptor=int(source['action_resolution']['descriptor'], 0),
        source_payload=int(source['action_resolution']['payload'], 0),
        source_motion=int(source['resources']['motion_object'], 0),
        source_timing=int(source['resources']['timing_object'], 0),
        source_motion_bank=int(sm['bank'], 0), source_timing_wrapper=int(st['wrapper'], 0),
        source_clip=int(sm['clip'], 0), source_timing_record=int(st['record'], 0),
        player_motion=int(player['resources']['motion_object'], 0),
        player_timing=int(player['resources']['timing_object'], 0))
    originals = pointer_slots(player, 'motion', [0, 4], 'bank') + pointer_slots(player, 'timing', [0, 3], 'wrapper')
    with LiveGame(p['session']['pid']) as game:
        if game.identity != p['session']:
            raise ValueError('Profile process identity changed')
        for who in ('source', 'player'):
            actor = p[who]
            raw, state = game.snapshot(int(actor['actor'], 0))
            if state['owner_like'] != actor['owner'] or [hex(U64(raw, 0x70+i*8)) for i in range(3)] != actor['action_banks']:
                raise ValueError('Actor/bank identity changed')
        for name, offset, expected in [
            ('source_owner', 0x38, fields['source_motion']), ('source_owner', 0x68, fields['source_timing']),
            ('player_owner', 0x38, fields['player_motion']), ('player_owner', 0x68, fields['player_timing']),
            ('source_motion', 8, fields['source_motion_bank']), ('source_timing', 0x10, fields['source_timing_wrapper'])]:
            if U64(game.bytes(fields[name]+offset, 8), 0) != expected:
                raise ValueError('Resource component changed')
        for address, expected in zip([fields['player_motion']+8, fields['player_motion']+0x28,
                                      fields['player_timing']+0x10, fields['player_timing']+0x28], originals):
            if U64(game.bytes(address, 8), 0) != expected:
                raise ValueError('Original resource slot changed')
        desc = game.bytes(fields['source_descriptor'], 0x44)
        if U32(desc, 0) != 0xC64 or not desc[0x40] or U64(desc, 0x20) != fields['source_payload']:
            raise ValueError('Source descriptor changed')
        if I32(game.bytes(fields['source_payload']+0x20, 4), 0) != 1220:
            raise ValueError('Source animation key changed')
    header = ['#pragma once', '// Session-bound preview only. Regenerate after any process/actor reload.',
              '#include <stdint.h>', 'struct BossSession {']
    header += [f'    uint64_t {name};' for name in fields]
    header += ['    uint64_t originals[4];', '};', 'static BossSession boss_session = {']
    header += [f'    0x{value:x}ULL, // {name}' for name, value in fields.items()]
    header += ['    {' + ', '.join(f'0x{v:x}ULL' for v in originals) + '}', '};', '']
    (ROOT / 'outputs/okatsu-prototype/native/boss_session.h').write_text('\n'.join(header))
    (ROOT / 'outputs/okatsu-prototype/boss-session.json').write_text(json.dumps(
        dict(session=p['session'], **fields, originals=originals, scope='Current process and encounter only'), indent=2))
    print(json.dumps(dict(prepared=True, pid=p['session']['pid'], fields=len(fields), slots=4)))


if __name__ == '__main__':
    main()
