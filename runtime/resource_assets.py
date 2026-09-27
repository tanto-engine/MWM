# Read supported game archive entries and compare their structure and file fingerprints.
# Product definitions supply identities; source bytes and ownership checks remain authoritative.
# See CODE_GUIDE.md for the player-readable flow and terminology.
import hashlib
import struct


def read_asset(folder, spec):
    # Read one verified source package from the installed archives.
    # Resolve its recorded archive entry and verify size and content hash.
    # Unexpected game data is rejected before entering a native decoder.
    path = folder / spec['archive']
    with path.open('rb') as stream:
        header = stream.read(32)
        if len(header) != 32 or header[:4] != b'K300':
            raise ValueError('Unrecognized archive header')
        count = struct.unpack_from('<q', header, 8)[0]
        if not 0 < count <= 200000 or not 0 <= spec['entry_id'] < count:
            raise ValueError('Archive entry bounds invalid')
        stream.seek(32 + spec['entry_id'] * 32)
        offset, size, uncompressed, flags = struct.unpack('<4q', stream.read(32))
        if (offset < 32 + count * 32 or size != spec['size'] or size != uncompressed
                or flags or size > 32 * 1024 * 1024 or offset + size > path.stat().st_size):
            raise ValueError('Unsupported archive extent/compression')
        stream.seek(offset)
        data = stream.read(size)
    if hashlib.sha256(data).hexdigest() != spec['sha256']:
        raise ValueError(f'Asset fingerprint mismatch: {spec["archive"]}/{spec["entry_id"]}')
    name_path = folder / spec['archive'].replace('archive_', 'lfm_order_').replace('.lnk', '.bin')
    names = name_path.read_bytes()
    fields = struct.unpack_from('<10I', names)
    count, table = fields[2], fields[4]
    if count > 200000 or table + count * 12 > len(names):
        raise ValueError('Name index bounds invalid')
    matches = []
    for index in range(count):
        _, entry_id, start = struct.unpack_from('<3I', names, table + index * 12)
        if entry_id != spec['entry_id']:
            continue
        end = names.find(b'\0', start, min(len(names), start + 4096))
        if end < start:
            raise ValueError('Name entry has no bounded terminator')
        matches.append(names[start:end].decode('ascii'))
    if matches != [spec['source_name']]:
        raise ValueError('Asset source identifier mismatch')
    return data
