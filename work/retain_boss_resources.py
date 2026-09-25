import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'runtime'))
from resource_assets import read_asset

archive = Path(r'C:\Program Files (x86)\Steam\steamapps\common\Nioh\archive')
recording = ROOT/'outputs/okatsu-prototype/recordings/maria-20260925-064124'
captured = {}
for path in recording.rglob('events.jsonl'):
    for row in map(json.loads, path.read_text().splitlines()):
        if row['kind']=='metadata' and row['role']!='player_candidate' and row['action_key_u32'] in (0xC75,0xC79,0x390):
            captured[row['action_key_u32']] = bytes.fromhex(row['payload_prefix']['bytes'])
assert len(captured)==3
wanted = {1000,1001,1002,1010,1020,1021,1022,1023,1030,1040,1100,1101,1120}
matches = {'actions': [], 'timing': [], 'motion': []}
for path in sorted(archive.glob('archive_*.lnk')):
    with path.open('rb') as stream:
        header=stream.read(32)
        assert header[:4]==b'K300'
        count=struct.unpack_from('<q',header,8)[0]
        entries=list(struct.iter_unpack('<4q',stream.read(count*32)))
        for index,(offset,size,uncompressed,flags) in enumerate(entries):
            if flags or size!=uncompressed or size<48:
                continue
            stream.seek(offset); head=stream.read(48)
            kind='timing' if head[:8]==b'TMG_PACK' else 'motion' if head[:8]==b'G2A_PACK' else None
            if kind:
                records=struct.unpack_from('<I',head,20)[0]
                at=struct.unpack_from('<I',head,40)[0]
                if at+8>size:
                    continue
                stream.seek(offset+at)
                slots,unused=struct.unpack('<2I',stream.read(8))
                if at+8+slots*8>size:
                    continue
                keys={key for key,position in struct.iter_unpack('<ii',stream.read(slots*8)) if position>=0}
                if len(wanted & keys)<10:
                    continue
            elif size<2000000 and head[:8]==bytes.fromhex('090000004c000000'):
                stream.seek(offset); data=stream.read(size)
                if not all(data.count(prefix)==1 for prefix in captured.values()):
                    continue
                kind='actions'
            else:
                continue
            spec=dict(archive=path.name,entry_id=index,size=size)
            if kind!='actions':
                spec.update(record_count=records,hash_slots=slots,format=head[:8].decode(),matched_keys=sorted(wanted & keys))
            matches[kind].append(spec)
print(json.dumps(matches,indent=2))
(ROOT/'work/maria-resource-candidates.json').write_text(json.dumps(matches,indent=2))

# Keep verified local source bytes beside their reproducible archive identities.
# Profiles stay authoritative; an asset copy is never accepted merely by filename.
inventory=[]
for profile_path in sorted((ROOT/'catalogue/resource_profiles').glob('*.json')):
    profile=json.loads(profile_path.read_text())
    folder=ROOT/'catalogue/resource_assets'/profile['boss_id']
    folder.mkdir(parents=True,exist_ok=True)
    for kind,spec in profile['assets'].items():
        data=read_asset(archive,spec)
        destination=folder/(kind+'.dat')
        destination.write_bytes(data)
        inventory.append(dict(boss_id=profile['boss_id'],kind=kind,path=destination.relative_to(ROOT).as_posix(),
                              size=len(data),sha256=hashlib.sha256(data).hexdigest(),profile=profile_path.relative_to(ROOT).as_posix()))
(ROOT/'catalogue/resource_assets/index.json').write_text(json.dumps(dict(assets=inventory),indent=2)+'\n')
