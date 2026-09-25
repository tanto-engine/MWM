"""Read-only reconstruction of the researched Nioh 1 action lookup.

Native function RVA 0x73FA40 searches three banks in order, their pointer arrays
at +0x128/count +0x130, tests descriptor byte +0x40, then compares its DWORD key.
This code enumerates data only; it never calls that native function.
"""
import argparse
import json
from pathlib import Path
from boss_probe import LiveGame, U32, U64, metadata, save_new


def inspect_banks(game, actor):
    before, state = game.snapshot(actor)
    context = before[0x70:0x88]
    banks = []
    for index in range(3):
        bank = U64(context, index * 8)
        item = dict(index=index, address=hex(bank), records=[])
        if bank:
            header = game.bytes(bank, 0x138)
            table, count = U64(header, 0x128), U32(header, 0x130)
            if count > 16384:
                raise ValueError('Bank count exceeds this research reader limit')
            item.update(table=hex(table), count=count)
            entries = game.bytes(table, count * 8) if count else b''
            for position in range(count):
                pointer = U64(entries, position * 8)
                if not pointer:
                    continue
                raw = game.bytes(pointer, 0x44)
                item['records'].append(dict(position=position, descriptor=hex(pointer),
                                             key_u32=U32(raw, 0), key_hex=f'0x{U32(raw, 0):08X}',
                                             enabled_byte=raw[0x40], payload=hex(U64(raw, 0x20))))
            if game.bytes(bank + 0x128, 12) != header[0x128:0x134]:
                raise ValueError('Bank pointer/count changed during inspection')
        banks.append(item)
    after, final = game.snapshot(actor)
    if after[0x70:0x88] != context or final['owner_like'] != state['owner_like']:
        raise ValueError('Actor lookup context changed during inspection')
    return dict(object=hex(actor), owner_like=state['owner_like'], banks=banks,
                consistency='Context and table headers rechecked; not an atomic snapshot')


def resolve(actor, key):
    if not 0 <= key <= 0xFFFFFFFF:
        raise ValueError('Lookup key must fit the native DWORD comparison')
    for bank in actor['banks']:
        for entry in bank['records']:
            if entry['enabled_byte'] and entry['key_u32'] == key:
                return dict(bank_index=bank['index'], bank_address=bank['address'], **entry)
    return None


def inspect_pair(game, source, destination, key):
    source_banks = inspect_banks(game, source)
    destination_banks = inspect_banks(game, destination)
    source_entry = resolve(source_banks, key)
    destination_entry = resolve(destination_banks, key)
    if source_entry is None:
        raise ValueError('Source key does not resolve in any enabled bank')
    data = metadata(game, int(source_entry['descriptor'], 0), 64)
    selected = bytes.fromhex(data['descriptor_bytes'])
    if (U32(selected, 0) != key or selected[0x40] != source_entry['enabled_byte']
            or U64(selected, 0x20) != int(source_entry['payload'], 0)):
        raise ValueError('Selected record changed before metadata inspection')
    # Signed transition keys are sign-extended by the native caller. -1 is a
    # rejected sentinel; other negative values must not silently wrap to uint16.
    targets = sorted({e['target_key_0x14_i16'] for e in data['transition_entries']
                      if 'target_key_0x14_i16' in e and e['target_key_0x14_i16'] != -1})
    comparisons = []
    for target in targets:
        lookup_key = target & 0xFFFFFFFF
        a, b = resolve(source_banks, lookup_key), resolve(destination_banks, lookup_key)
        comparisons.append(dict(transition_key_i16=target, source=a, destination=b,
                                same_descriptor=bool(a and b and a['descriptor'] == b['descriptor'])))
    return dict(session=game.identity, source_actor=source_banks, destination_actor=destination_banks,
                key_u32=key, source_resolution=source_entry, destination_resolution=destination_entry,
                source_metadata=data, direct_transition_comparisons=comparisons,
                native_lookup_rva='0x73FA40', game_modified=False,
                unresolved=['Move visual identity', 'Animation binding and skeleton compatibility',
                            'Hit events and player-owned damage', 'Transition policy and asset lifetime'])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pid', required=True, type=int)
    p.add_argument('--source', required=True, type=lambda x: int(x, 0))
    p.add_argument('--destination', required=True, type=lambda x: int(x, 0))
    p.add_argument('--key', required=True, type=lambda x: int(x, 0))
    p.add_argument('--out', required=True, type=Path)
    args = p.parse_args()
    if args.out.exists():
        p.error('Choose a new output path')
    with LiveGame(args.pid) as game:
        game.begin_sample()
        result = inspect_pair(game, args.source, args.destination, args.key)
    save_new(args.out, result)
    print(json.dumps({k: result[k] for k in ('source_resolution', 'destination_resolution')}, indent=2))
    print(json.dumps(dict(direct_target_keys=len(result['direct_transition_comparisons']),
                          same_descriptor=sum(x['same_descriptor'] for x in result['direct_transition_comparisons']),
                          missing_in_player=sum(x['destination'] is None for x in result['direct_transition_comparisons']))))


if __name__ == '__main__':
    main()
