"""Bounded read-only name/header inspection; never extracts or rewrites archives."""
import json
from pathlib import Path
import struct

folder = Path('C:/Program Files (x86)/Steam/steamapps/common/Nioh/archive')
result = []
for names in sorted(folder.glob('lfm_order_*.bin')):
    raw = names.read_bytes()
    if len(raw) < 40:
        continue
    header = struct.unpack_from('<10I', raw)
    count, at = header[2], header[4]
    if count > 200000 or at + count * 12 > len(raw):
        raise ValueError(f'Unexpected name-table bounds: {names.name}')
    entries = []
    for index in range(count):
        reserved, file_id, name_at = struct.unpack_from('<III', raw, at + index * 12)
        if name_at >= len(raw):
            raise ValueError('Name pointer outside name file')
        end = raw.find(b'\0', name_at, min(len(raw), name_at + 4096))
        if end < 0:
            raise ValueError('Missing bounded string terminator')
        text = raw[name_at:end].decode('utf8', errors='replace')
        entries.append(dict(file_id=file_id, name=text))
    archive = folder / names.name.replace('lfm_order_', 'archive_').replace('.bin', '.lnk')
    with archive.open('rb') as f:
        ah = f.read(32)
        magic, zero, files, size, align = struct.unpack('<IIqqq', ah)
        if not 0 <= files <= 200000:
            raise ValueError('Unexpected archive index size')
        index_data = f.read(files * 32)
        compression = {}
        for i in range(files):
            flag = struct.unpack_from('<q', index_data, i * 32 + 24)[0]
            compression[str(flag)] = compression.get(str(flag), 0) + 1
    hits = [e for e in entries if any(x in e['name'].lower() for x in ('okatsu', 'okatu', '.g1a', '.g2a'))]
    result.append(dict(archive=archive.name, named_entries=len(entries), archive_entries=files,
                       compression_flags=compression, sample_names=entries[:6], matching_names=hits[:40]))
Path('work/nioh-asset-index-inspection.json').write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
