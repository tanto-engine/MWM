# Verify researched Okatsu asset identities from local archives, without extraction or game access.
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]


import sys
sys.path.insert(0, str(ROOT / "runtime"))
from resource_assets import read_asset


def lookup_record(data, spec, key):
    # Resolve a package key through its bounded hash and offset tables.
    # Check file size, record count and record extents against the manifest.
    # Reject corrupt archives before comparing captured resource bytes.
    if len(data) < 48 or data[:8].decode('ascii') != spec['format']:
        raise ValueError('Package type mismatch')
    size, count = struct.unpack_from('<2I', data, 16)
    offsets, sizes, hash_at = struct.unpack_from('<3I', data, 32)
    if size != len(data) or count != spec['record_count'] or count > 32768:
        raise ValueError('Package record count/size mismatch')
    if any(at < 48 or at + count * 4 > len(data) for at in (offsets, sizes)) or hash_at + 8 > len(data):
        raise ValueError('Package table bounds invalid')
    slots = struct.unpack_from('<I', data, hash_at)[0]
    if slots != spec['hash_slots'] or hash_at + 8 + slots * 8 > len(data):
        raise ValueError('Package hash extent mismatch')
    hits = [index for found, index in struct.iter_unpack('<ii', data[hash_at + 8:hash_at + 8 + slots * 8]) if found == key]
    if len(hits) != 1 or not 0 <= hits[0] < count:
        raise ValueError('Package key is absent or ambiguous')
    index = hits[0]
    at = struct.unpack_from('<I', data, offsets + index * 4)[0]
    size = struct.unpack_from('<I', data, sizes + index * 4)[0]
    if not at or not size or at + size > len(data):
        raise ValueError('Package record bounds invalid')
    return index, at, data[at:at + size]


def verify(folder, manifest, capture):
    # Compare archive records against saved Okatsu payload and timing evidence.
    # Check asset hashes, record locations and full timing event sequences.
    # Establish asset identity without claiming runtime loading or combat readiness.
    data = {kind: read_asset(folder, spec) for kind, spec in manifest['assets'].items()}
    payload = bytes.fromhex(capture['source']['payload_bytes'])
    if data['actions'].count(payload) != 1 or data['actions'].find(payload) != 17852:
        raise ValueError('Saved C64 payload does not uniquely match the action package')
    observed = {'C64': capture['source']['resources']['timing']['banks'][0],
                'C66': capture['charged_candidate']['timing_resource']}
    result = {}
    for name, move in manifest['moves'].items():
        row = {}
        for kind in ('timing', 'motion'):
            index, at, record = lookup_record(data[kind], manifest['assets'][kind], move[kind + '_key'])
            if index != move[kind + '_index'] or at != move[kind + '_record_offset']:
                raise ValueError('Saved motion/timing location differs')
            row[kind] = dict(key=move[kind + '_key'], index=index, package_offset=at,
                             record_sha256=hashlib.sha256(record).hexdigest())
            if kind == 'timing':
                count, event_at = struct.unpack_from('<2I', record, 4)
                if count != move['timing_event_count'] or event_at + count * 12 > len(record):
                    raise ValueError('Timing event extent differs')
                if record[event_at:event_at + count * 12] != bytes.fromhex(observed[name]['events']):
                    raise ValueError('Full timing event sequence differs from the encounter capture')
            elif name == 'C66':
                live = bytes.fromhex(capture['charged_candidate']['motion_resource']['clip_prefix'])
                if (struct.unpack_from('<f', record, 12)[0] != struct.unpack_from('<f', live, 24)[0]
                        or struct.unpack_from('<H', record, 16)[0] != struct.unpack_from('<H', live, 28)[0]):
                    raise ValueError('C66 motion metadata differs from the decoded clip capture')
        result[name] = row
    return dict(status='asset_identities_verified', resource_profile_id=manifest['resource_profile_id'],
                runtime_loading_verified=False, game_access=False, raw_assets_saved=False, moves=result)


def main():
    # Run the archive audit with explicit or configured local paths.
    # Read the maintained resource profile and saved capture.
    # Keep this verification offline and avoid extracting game assets.
    parser = argparse.ArgumentParser(description='Verify Okatsu resource identities in local archives.')
    game = Path(os.environ.get('NIOH_EXE', r'C:\Program Files (x86)\Steam\steamapps\common\Nioh\nioh.exe'))
    parser.add_argument('--archive', type=Path, default=game.parent / 'archive')
    parser.add_argument('--profile', type=Path, default=ROOT / 'catalogue/resource_profiles/okatsu.json')
    parser.add_argument('--capture', type=Path, default=ROOT / 'work/native-tests/fixtures/session-profile.json')
    args = parser.parse_args()
    print(json.dumps(verify(args.archive, json.loads(args.profile.read_text()),
                            json.loads(args.capture.read_text())), indent=2))


if __name__ == '__main__':
    main()
