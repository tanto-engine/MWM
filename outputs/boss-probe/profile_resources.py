# Read-only, fresh-session action/motion/timing resource comparison.
#
# Heap addresses come exclusively from --discovery. Role names mean matching the
# researched C64 motion fingerprints, not an independently proven character ID.
import argparse
import ctypes as C
from ctypes import wintypes as W
import json
from pathlib import Path
import struct
import sys
import time

from boss_probe import LiveGame, U32, I32, U64, kernel, save_new
from action_banks import inspect_banks, resolve
from motion_resources import motion_lookup
from timing_resources import lookup as timing_lookup

ACTION_KEY = 0xC64
ROLE_KEYS = {1220: 'boss_fingerprint', 2033: 'player_fingerprint'}


def birth(game):
    # Read the process creation time through its existing handle.
    # Combine the FILETIME words into one stable identity value.
    # Distinguish a restarted executable from a reused PID.
    values = [W.FILETIME() for _ in range(4)]
    if not kernel.GetProcessTimes(game.handle, *(C.byref(v) for v in values)):
        raise C.WinError(C.get_last_error())
    return str((values[0].dwHighDateTime << 32) | values[0].dwLowDateTime)


def validate_discovery(game, discovery):
    # Compare discovery provenance against the current process and build.
    # Recheck creation time and liveness before resource profiling.
    # Prevent saved heap addresses from crossing process lifetimes.
    for key in ('pid', 'creation_filetime', 'build_sha256', 'module_base', 'vtable'):
        if str(discovery.get(key)) != str(game.identity[key]):
            raise ValueError(f'Discovery session mismatch: {key}')
    if birth(game) != game.identity['creation_filetime'] or not game.alive():
        raise ValueError('Process identity changed or exited')


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


def summarize(rows):
    # Separate present slots from unresolved resource observations.
    # Claim absence only when every slot has a definite absent result.
    # Keep read failures from becoming false missing-resource conclusions.
    present = [r['slot'] for r in rows if r['presence'] == 'present']
    unknown = [r['slot'] for r in rows if r['presence'] not in ('present', 'absent', 'empty_slot')]
    return dict(present_slots=present, unresolved_slots=unknown,
                absent_from_all_loaded_banks=not present and not unknown)


def profile(game, discovery):
    # Compare boss and player fingerprints within one process lifetime.
    # Cache repeated resource lookups and recheck all pinned ranges.
    # Produce research evidence for dependencies and missing player resources.
    validate_discovery(game, discovery)
    game.begin_sample()
    stable = StableReads(game)
    candidates = discovery.get('candidates', [])
    if not 1 <= len(candidates) <= 256:
        raise ValueError(f'Found {len(candidates)} candidates; expected 1..256')
    addresses = [int(c['object'], 0) for c in candidates]
    if len(set(addresses)) != len(addresses):
        raise ValueError('Discovery contains duplicate actor pointers')
    inspected = [inspect_candidate(game, stable, candidate) for candidate in candidates]
    selected = {}
    for key, role in ROLE_KEYS.items():
        matches = [a for a in inspected if a['role'] == role]
        if len(matches) != 1:
            raise ValueError(f'Expected exactly one C64 motion-{key} fingerprint, found {len(matches)}')
        selected[role] = matches[0]
    source = selected['boss_fingerprint']
    motion_key = source['motion_key']
    timing_key = motion_key if source['timing_key'] < 0 else source['timing_key']
    source['effective_timing_key'] = timing_key
    source['timing_key_rule'] = 'payload+0x34 < 0 uses motion key; verified native RVA0x6FF7C3..0x6FF7DB'
    cache = {}
    def lookup_resources(motion_banks, timing_banks, wanted_motion, wanted_timing):
        # Resolve requested motion and timing keys across each populated slot.
        # Cache by resource kind, pointer and key within this profile.
        # Retain per-slot failures without repeatedly reading shared banks.
        info = {}
        for kind, banks, key, inspect in [('motion', motion_banks, wanted_motion, inspect_motion),
                                          ('timing', timing_banks, wanted_timing, inspect_timing)]:
            rows = []
            for slot, pointer in enumerate(banks):
                if not pointer:
                    rows.append(dict(slot=slot, presence='empty_slot'))
                    continue
                cache_key = (kind, pointer, key)
                if cache_key not in cache:
                    try:
                        cache[cache_key] = inspect(game, stable, pointer, key)
                    except (ValueError, OSError) as error:
                        cache[cache_key] = dict(address=hex(pointer), presence='read_error', error=str(error))
                rows.append(dict(slot=slot, **cache[cache_key]))
            info[kind] = dict(lookup_key=key, banks=rows, **summarize(rows))
        return info
    for actor in selected.values():
        info, motion_banks, timing_banks = resources(game, stable, actor)
        info.update(lookup_resources(motion_banks, timing_banks, motion_key, timing_key))
        for target in actor.get('target_actions', []):
            if target['resolution']:
                target['resources'] = lookup_resources(motion_banks, timing_banks,
                                                      target['motion_key'], target['effective_timing_key'])
        actor['resources'] = info
    stable.check()
    validate_discovery(game, discovery)
    player = selected['player_fingerprint']
    return dict(session=game.identity, recorded_at=time.time(), action_key=ACTION_KEY,
                compact_config=dict(player_actor=player['actor'], player_owner=player['owner'],
                                    player_action_context=player['action_context'], player_action_banks=player['action_banks'],
                                    source_actor=source['actor'], source_owner=source['owner'],
                                    source_action_context=source['action_context'], source_action_banks=source['action_banks'],
                                    source_descriptor=source['action_resolution']['descriptor'],
                                    source_payload=source['action_resolution']['payload']),
                source=selected['boss_fingerprint'], player=selected['player_fingerprint'],
                other_fingerprints=[dict(actor=a['actor'], role=a['role'], motion_key=a.get('motion_key'))
                                    for a in inspected if a['role'] == 'unmatched'],
                consistency=dict(process_birth_rechecked=True, stable_ranges=len(stable.ranges),
                                 owner_action_and_resource_identities_rechecked=True,
                                 atomic_snapshot=False),
                role_basis='C64 motion-key fingerprints: 1220 boss, 2033 player; not an independent character ID',
                game_modified=False)


def main():
    # Run an explicit read-only resource comparison from saved discovery.
    # Require matching PID and a new output destination.
    # Leave production attachment to the engine supervisor.
    parser = argparse.ArgumentParser(description='Compare action, motion and timing resource metadata.')
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--discovery', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error('Choose a new output path')
    discovery = json.loads(args.discovery.read_text())
    if discovery.get('pid') != args.pid:
        parser.error('PID must match the discovery file')
    with LiveGame(args.pid) as game:
        result = profile(game, discovery)
    save_new(args.out, result)
    print(json.dumps(dict(out=str(args.out), source=result['source']['actor'], player=result['player']['actor'],
                          source_motion=result['source']['resources']['motion']['present_slots'],
                          source_timing=result['source']['resources']['timing']['present_slots'],
                          player_motion_absent=result['player']['resources']['motion']['absent_from_all_loaded_banks'],
                          player_timing_absent=result['player']['resources']['timing']['absent_from_all_loaded_banks'],
                          stable_ranges=result['consistency']['stable_ranges'])))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, struct.error) as error:
        print(json.dumps(dict(status='error', message=str(error))), file=sys.stderr)
        raise SystemExit(1)
