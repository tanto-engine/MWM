# Inspect player action, motion and timing resources using verified live identities.
# Every retained byte range is rechecked before session preparation completes.
import struct

from boss_probe import U32, I32, U64
from action_banks import inspect_banks, resolve
from motion_resources import motion_lookup
from timing_resources import lookup as timing_lookup

ACTION_KEY = 0xC64
ROLE_KEYS = {1220: 'boss_fingerprint', 2033: 'player_fingerprint'}


class StableReads:
    def __init__(self, game):
        # Start a registry of byte ranges that define resource identity.
        # Share the caller's read-only game connection.
        # Later checks compare the same ranges after dependent reads finish.
        self.game = game
        self.ranges = {}

    def pin(self, address, count, expected=None):
        # Read and retain a resource range under its address and length.
        # Compare repeated reads or supplied expected bytes immediately.
        # Detect replacement before mixing old and new resource structures.
        if not count:
            return b''
        raw = self.game.bytes(address, count)
        previous = self.ranges.get((address, count), expected)
        if previous is not None and raw != previous:
            raise ValueError(f'Resource identity changed at {address:#x}')
        self.ranges[address, count] = raw
        return raw

    def check(self):
        # Re-read every retained identity range using fresh region queries.
        # Fail when any bytes differ from the recorded profile.
        # Bracket a multi-object inspection without claiming atomicity.
        self.game.begin_sample()
        for (address, count), expected in self.ranges.items():
            if self.game.bytes(address, count) != expected:
                raise ValueError(f'Resource identity changed during profile at {address:#x}')


def inspect_candidate(game, stable, candidate):
    # Resolve the researched action key for one discovered actor.
    # Pin owner, bank tables and selected descriptor identities.
    # Classify fingerprints while retaining unmatched actor evidence.
    actor = int(candidate['object'], 0)
    before, state = game.snapshot(actor)
    owner = int(state['owner_like'], 0)
    if candidate.get('owner_like') != state['owner_like']:
        raise ValueError(f'Discovered owner changed for {actor:#x}')
    stable.pin(actor, 8, before[:8])
    stable.pin(actor + 0x50, 8, before[0x50:0x58])
    stable.pin(actor + 0x70, 24, before[0x70:0x88])
    banks = inspect_banks(game, actor)
    selected = resolve(banks, ACTION_KEY)
    # Reconstruct the scanned pointer array, including its null entries, so a
    # changed table cannot silently change which enabled entry resolved first.
    for bank in banks['banks']:
        if not int(bank['address'], 0):
            continue
        address = int(bank['address'], 0)
        table, count = int(bank['table'], 0), bank['count']
        stable.pin(address + 0x128, 12, struct.pack('<QI', table, count))
        pointers = bytearray(count * 8)
        for entry in bank['records']:
            struct.pack_into('<Q', pointers, entry['position'] * 8, int(entry['descriptor'], 0))
        stable.pin(table, count * 8, bytes(pointers))
    row = dict(actor=hex(actor), owner=hex(owner), role='unmatched',
               action_key=ACTION_KEY, action_resolution=selected,
               action_context=hex(actor + 0x70),
               action_banks=[b['address'] for b in banks['banks']])
    if selected is None:
        return row
    descriptor = int(selected['descriptor'], 0)
    payload = int(selected['payload'], 0)
    desc = stable.pin(descriptor, 0xD0)
    body = stable.pin(payload, 0x38)
    if U32(desc, 0) != ACTION_KEY or desc[0x40] != selected['enabled_byte'] or U64(desc, 0x20) != payload:
        raise ValueError('C64 descriptor changed since action lookup')
    motion_key, timing_key = I32(body, 0x20), I32(body, 0x34)
    row.update(role=ROLE_KEYS.get(motion_key, 'unmatched'), motion_key=motion_key,
               timing_key=timing_key, descriptor_bytes=desc.hex(), payload_bytes=body.hex())
    if row['role'] == 'player_fingerprint':
        row['target_actions'] = []
        for key in (0xCF0, 0xD34):
            entry = resolve(banks, key)
            target = dict(action_key=key, action_key_hex=hex(key), resolution=entry)
            if entry:
                prefix = stable.pin(int(entry['descriptor'], 0), 0xD0)
                payload_prefix = stable.pin(int(entry['payload'], 0), 0x38)
                if U32(prefix, 0) != key or not prefix[0x40] or U64(prefix, 0x20) != int(entry['payload'], 0):
                    raise ValueError('Target action descriptor changed')
                motion_key, timing_override = I32(payload_prefix, 0x20), I32(payload_prefix, 0x34)
                target.update(motion_key=motion_key, timing_override=timing_override,
                              effective_timing_key=motion_key if timing_override < 0 else timing_override,
                              descriptor_bytes=prefix.hex(), payload_bytes=payload_prefix.hex())
            row['target_actions'].append(target)
    return row


def resources(game, stable, actor):
    # Read motion and timing components from a verified actor owner.
    # Pin their slot arrays and sample current playback separately.
    # Separate stable dependencies from transient animation state.
    owner = int(actor['owner'], 0)
    motion = U64(stable.pin(owner + 0x38, 8), 0)
    timing = U64(stable.pin(owner + 0x68, 8), 0)
    if not motion or not timing:
        raise ValueError('Expected actor resource object is absent')
    motion_slots = stable.pin(motion + 8, 8 * 8)
    timing_slots = stable.pin(timing + 0x10, 6 * 8)
    dynamic = game.bytes(motion, 0x108)
    row = dict(motion_object=hex(motion), timing_object=hex(timing),
               sampled_motion_group=I32(dynamic, 0x50), sampled_motion_bank=I32(dynamic, 0x48),
               sampled_motion_key=I32(dynamic, 0xEC), sampled_motion_clip=hex(U64(dynamic, 0x58)))
    return row, [U64(motion_slots, i * 8) for i in range(8)], [U64(timing_slots, i * 8) for i in range(6)]


def pin_hash(stable, table):
    # Retain a bounded key-to-index table and its header.
    # Reject implausible counts before copying the entry array.
    # Resource lookups depend on both header and entry stability.
    head = stable.pin(table, 24)
    count, pairs = U32(head, 8), U64(head, 16)
    if not 0 < count <= 32768:
        raise ValueError('Resource hash count outside researched bounds')
    stable.pin(pairs, count * 8)


def inspect_motion(game, stable, bank, key):
    # Inspect one motion lookup while pinning its dependent pointers.
    # Classify absence, ambiguity and empty clips explicitly.
    # Avoid treating a failed lookup as proof that an asset is absent.
    tail = stable.pin(bank + 0x468, 0x20)
    array, table = U64(tail, 0), U64(tail, 0x18)
    pin_hash(stable, table)
    result = motion_lookup(game, bank, key)
    if len(result['matches']) == 0:
        result['presence'] = 'absent'
    elif len(result['matches']) != 1:
        result['presence'] = 'ambiguous'
    else:
        pointer = U64(stable.pin(array + result['index'] * 8, 8), 0)
        if hex(pointer) != result['clip']:
            raise ValueError('Clip pointer changed')
        result['presence'] = 'present' if pointer else 'empty_pointer'
    result.pop('clip_prefix', None)
    return result


def inspect_timing(game, stable, wrapper, key):
    # Inspect one timing lookup and pin its event record dependencies.
    # Follow relative offsets only after the shared lookup validates them.
    # Detect changed timing data before accepting the profile.
    head = stable.pin(wrapper, 16)
    data, table = U64(head, 0), U64(head, 8)
    pin_hash(stable, table)
    result = timing_lookup(game, wrapper, key)
    if not result['indexes']:
        result['presence'] = 'absent'
    elif len(result['indexes']) != 1:
        result['presence'] = 'ambiguous'
    elif 'record' not in result:
        result['presence'] = 'unresolved_entry'
    else:
        data_head = game.bytes(data, 0x24)
        stable.pin(data + 0x14, 4, data_head[0x14:0x18])
        stable.pin(data + 0x20, 4, data_head[0x20:0x24])
        relative = U32(stable.pin(data + U32(data_head, 0x20) + result['indexes'][0] * 4, 4), 0)
        if hex(data + relative) != result['record']:
            raise ValueError('Timing record pointer changed')
        record = int(result['record'], 0)
        prefix = stable.pin(record, 16, bytes.fromhex(result['prefix']))
        stable.pin(record + U32(prefix, 8), result['event_count'] * 12, bytes.fromhex(result['events']))
        result['presence'] = 'present'
    return result
