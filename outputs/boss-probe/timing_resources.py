"""Read-only timing resource lookup; callers supply all live addresses."""
from boss_probe import U32, I32, U64

def lookup(game, wrapper, key):
    head = game.bytes(wrapper, 16)
    data, table = U64(head, 0), U64(head, 8)
    hash_head = game.bytes(table, 24)
    count, pairs = U32(hash_head, 8), U64(hash_head, 16)
    if not 0 < count <= 32768:
        raise ValueError('Invalid hash table count')
    raw = game.bytes(pairs, count*8)
    indexes = [I32(raw, at+4) for at in range(0, len(raw), 8) if I32(raw, at) == key]
    row = dict(wrapper=hex(wrapper), hash_slots=count, indexes=indexes)
    if len(indexes) != 1 or indexes[0] < 0:
        return row
    data_head = game.bytes(data, 0x24)
    entries, offsets = U32(data_head, 0x14), U32(data_head, 0x20)
    if indexes[0] >= entries or not offsets:
        raise ValueError('Timing record index/offset invalid')
    relative = U32(game.bytes(data+offsets+indexes[0]*4, 4), 0)
    if not relative:
        return row
    record = data+relative
    prefix = game.bytes(record, 0x10)
    event_count, event_offset = U32(prefix, 4), U32(prefix, 8)
    if event_count > 512 or event_offset > 0x100000:
        raise ValueError('Timing entry bound exceeded')
    row.update(record=hex(record), prefix=prefix.hex(), event_count=event_count,
               events=game.bytes(record+event_offset, event_count*12).hex() if event_count else '')
    if game.bytes(wrapper, 16) != head or game.bytes(table, 24) != hash_head:
        raise ValueError('Timing identity changed')
    return row
