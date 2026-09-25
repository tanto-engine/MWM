import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
folder = Path('C:/Program Files (x86)/Steam/steamapps/common/Nioh/archive')
source = json.loads((ROOT/'outputs/okatsu-prototype/recordings/jin-hayabusa-20260925-062619/source-bank-research.json').read_text())
source_keys = {row['motion_id'] for row in source['banks'][1]['records'] if row['motion_id'] >= 0}
requested = {5010,5012,5013,5020,5180,5110,5111,2400,2410,2420}
counts = {'G2A_PACK': 0, 'TMG_PACK': 0}
matches = []
neighbors = []
for path in sorted(folder.glob('archive_*.lnk')):
    with path.open('rb') as stream:
        header = stream.read(32)
        assert header[:4] == b'K300'
        count = struct.unpack_from('<q', header, 8)[0]
        assert 0 < count <= 200000
        entries = list(struct.iter_unpack('<4q', stream.read(count*32)))
        for index, (offset,size,uncompressed,flags) in enumerate(entries):
            if flags or size != uncompressed or not 48 <= size <= 32*1024*1024:
                continue
            stream.seek(offset)
            prefix = stream.read(48)
            if prefix[:8] not in (b'G2A_PACK', b'TMG_PACK'):
                continue
            kind = prefix[:8].decode('ascii')
            counts[kind] += 1
            package_size, records = struct.unpack_from('<2I',prefix,16)
            offsets,sizes,mapping = struct.unpack_from('<3I',prefix,32)
            assert package_size == size and records <= 32768 and mapping+8 <= size
            stream.seek(offset+mapping)
            slots = struct.unpack('<I',stream.read(4))[0]
            stream.read(4)
            assert slots <= 65536 and mapping+8+slots*8 <= size
            keys = {key:slot for key,slot in struct.iter_unpack('<ii',stream.read(slots*8)) if key >= 0 and slot >= 0}
            nearby = path.name == 'archive_01.lnk' and 4310 <= index <= 4350
            if nearby:
                neighbors.append(dict(archive=path.name,entry_id=index,format=kind,records=records,keys=sorted(keys)))
            if 5180 not in keys and not nearby:
                continue
            selected = {}
            for key in sorted(requested & keys.keys()):
                slot = keys[key]
                assert slot < records
                stream.seek(offset+offsets+slot*4); start=struct.unpack('<I',stream.read(4))[0]
                stream.seek(offset+sizes+slot*4); extent=struct.unpack('<I',stream.read(4))[0]
                assert start+extent <= size
                stream.seek(offset+start);record=stream.read(extent)
                value=dict(size=extent,sha256=hashlib.sha256(record).hexdigest())
                if kind == 'G2A_PACK':value['frames']=struct.unpack_from('<H',record,16)[0]
                else:value['event_count']=struct.unpack_from('<I',record,4)[0]
                selected[str(key)] = value
            matches.append(dict(archive=path.name,entry_id=index,format=kind,records=records,
                                source_keys_matched=len(source_keys & keys.keys()),selected=selected))
result = dict(scope='Offline package scan; key overlap cannot prove which native boss resource slot supplied an action.',
              package_counts=counts,source_unique_motion_keys=len(source_keys),matches=matches,neighbors=neighbors)
(ROOT/'work/jin-resource-identity-scan.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(dict(package_counts=counts,matches=matches),indent=2))
