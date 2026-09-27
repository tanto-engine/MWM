"""Reproduce the new sword trials from archived observations and installed game assets."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zipfile

ROOT = Path(__file__).resolve().parents[1]
# Action packages match complete recorded payload prefixes. Companion packs were
# reviewed against their motion-key sets and adjacent motion/camera package layout.
# These identities permit an in-game trial; they do not certify visual/contact behavior.
SOURCES = {
    'toyotomi_hideyori': (147, 4048, [0xD30, 0xD31, 0xD32, 0xD33]),
    'oda_nobunaga': (103, 3996, [0xC6E, 0xC6F]),
    'tachibana_muneshige': (107, 4005, [0xD8D]),
    'sanada_yukimura': (134, 4038, [0xC6A]),
}


def asset(folder, archive, index):
    # Read an uncompressed installed asset without exporting copyrighted package bytes.
    # Keep its original lookup name and content hash so preparation verifies the same file.
    # The existing native resource loader consumes this identity, not a boss actor pointer.
    with (folder/archive).open('rb') as stream:
        assert stream.read(4) == b'K300'
        stream.seek(32+index*32)
        offset, size, plain, flags = struct.unpack('<4q', stream.read(32))
        if size != plain or flags: raise ValueError('Trial requires an uncompressed asset')
        stream.seek(offset); data = stream.read(size)
    names = (folder/archive.replace('archive_', 'lfm_order_').replace('.lnk', '.bin')).read_bytes()
    count, table = struct.unpack_from('<I', names, 8)[0], struct.unpack_from('<I', names, 16)[0]
    matches = [start for _, entry, start in struct.iter_unpack('<3I', names[table:table+count*12]) if entry == index]
    if len(matches) != 1: raise ValueError('Asset must have one native lookup name')
    name = names[matches[0]:names.index(b'\0', matches[0])].decode('ascii')
    return data, dict(archive=archive, entry_id=index, source_name=name, size=size, sha256=hashlib.sha256(data).hexdigest())


def records(data):
    # Decode the packaged key-to-index map and per-record relative offsets.
    # This is the serialized counterpart of Engine's native motion/timing lookups.
    # Reject malformed indices before using them to identify source animation data.
    if data[:8] not in (b'TMG_PACK', b'G2A_PACK'): raise ValueError('Unexpected resource package')
    count, offsets, table = (struct.unpack_from('<I', data, at)[0] for at in (20, 32, 40))
    slots = struct.unpack_from('<I', data, table)[0]
    result = {}
    for key, index in struct.iter_unpack('<ii', data[table+8:table+8+slots*8]):
        if key < 0: continue
        if key in result or not 0 <= index < count: raise ValueError('Ambiguous resource key')
        offset = struct.unpack_from('<I', data, offsets+index*4)[0]
        if not 0 < offset < len(data): raise ValueError('Invalid resource record')
        result[key] = (index, offset)
    return result


def observations(boss):
    # Resolve each selected action from the immutable evidence already in this repository.
    # Retain its complete payload prefix and metadata, not an inferred visual hit count.
    # Repeated evidence must agree on source bytes before it becomes an import definition.
    found = {}
    for file in (ROOT/'dataset/weapons').glob(f'*/{boss}/*.json'):
        move = json.loads(file.read_text(encoding='utf8'))
        for evidence in move['evidence']:
            with zipfile.ZipFile(ROOT/'dataset/evidence'/f"{evidence['archive_sha256']}.zip") as archive:
                journal = next(name for name in archive.namelist() if name.endswith('events.jsonl'))
                rows = [json.loads(line) for line in archive.read(journal).splitlines()]
            for step in evidence['steps']:
                row = rows[step['metadata_line']-1]
                key = row['action_key_u32']
                if key in found and found[key]['payload_prefix']['bytes'] != row['payload_prefix']['bytes']:
                    raise ValueError('Conflicting source payload observations')
                found[key] = row
    return found


def write(path, value):
    # Publish deterministic JSON definitions for normal source review.
    # Generated files contain identifiers/hashes rather than extracted game resources.
    # The original recordings and installed archives are never modified.
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n', encoding='utf8')


def compile_sources(folder):
    # Match recorded action bytes, resolve companion resources and author the requested trials.
    # Keep original source recovery and event signatures separate from runtime adaptation.
    # Every generated definition remains explicitly unverified in gameplay.
    catalogue = json.loads((ROOT/'data/moves.json').read_text(encoding='utf8'))
    for boss, (action_index, timing_index, keys) in SOURCES.items():
        observed = observations(boss)
        actions, action_asset = asset(folder, 'archive_00.lnk', action_index)
        timing, timing_asset = asset(folder, 'archive_01.lnk', timing_index)
        motion, motion_asset = asset(folder, 'archive_01.lnk', timing_index+1)
        _, camera_asset = asset(folder, 'archive_01.lnk', timing_index+2)
        timing_map, motion_map = records(timing), records(motion)
        profile = dict(schema_version=1, resource_profile_id=f'{boss}.resources.v1', boss_id=boss,
                       build_sha256=catalogue['supported_build_sha256'], status='archive_matched_gameplay_trial',
                       cold_launch_supported=False, assets=dict(actions=action_asset, timing=timing_asset, motion=motion_asset, camera=camera_asset), moves={})
        imports = []
        for key in keys:
            row = observed[key]; prefix = bytes.fromhex(row['payload_prefix']['bytes'])
            at = actions.find(prefix)
            if at < 0 or actions.find(prefix, at+1) >= 0: raise ValueError(f'{boss}/{key:X}: payload is not a unique archive match')
            body = actions[at:at+176]
            motion_key = row['payload_prefix']['motion_id']
            mi, mo = motion_map[motion_key]; ti, to = timing_map[motion_key]
            count, events_offset, sound_offset = (struct.unpack_from('<I', timing, to+offset)[0] for offset in (4,8,16))
            events = list(struct.iter_unpack('<III', timing[to+events_offset:to+events_offset+count*12]))
            voices = []
            for frame, kind, index in events:
                if kind != 10: continue
                sound = to+sound_offset+index*76
                if struct.unpack_from('<I', timing, sound+64)[0] == 12:
                    voices.append(dict(frame=frame,index=index,hash=struct.unpack_from('<I',timing,sound+28)[0]))
            if len(voices)>3: raise ValueError(f'{boss}/{key:X}: voice adapter needs more than three events')
            identifier = f'{boss}.action_{key:04x}'
            move = dict(id=identifier,key=key,motion=motion_key,flags=struct.unpack_from('<Q',body,24)[0],
                        ki_cost=struct.unpack_from('<h',body,22)[0],recovery_frame=struct.unpack_from('<h',body,36)[0],
                        transition_count=row['transition_slice']['count'],next=None,next_start=0,next_end=0,voices=voices,
                        source_payload_prefix=prefix.hex(),adapter_kind=2 if key==keys[0] else 4,
                        replacement=dict(player_key=0xCF5,player_motion=4300,transition_count=46,recovery_frame=38))
            imports.append(move)
            profile['moves'][f'{key:X}'] = dict(motion_key=motion_key,timing_key=motion_key,motion_index=mi,motion_record_offset=mo,
                                                timing_index=ti,timing_record_offset=to,timing_event_count=count,
                                                source_payload_offset=at)
            if not any(item['id']==identifier for item in catalogue['moves']):
                catalogue['moves'].append(dict(id=identifier,name=boss.replace('_',' ').title()+f' · {key:04X} trial',boss_id=boss,
                    weapon='sword',designation='skill',source=dict(action_id=key,action_hex=f'{key:04X}',motion_id=motion_key,
                    timing_id=motion_key,flags=move['flags'],ki_cost=move['ki_cost'],recovery_frame=move['recovery_frame']),
                    default_binding=None,implementation=dict(selectable=True,engine_profile='recorded_grounded_trial'),
                    adaptation=dict(status='experimental'),verification=dict(gameplay='pending')))
        if not any(item['id']==boss for item in catalogue['bosses']): catalogue['bosses'].append(dict(id=boss,name=boss.replace('_',' ').title()))
        write(ROOT/'data/resources'/f'{boss}.json', profile)
        write(ROOT/'data/imports'/f'{boss}.json',dict(schema_version=1,boss_id=boss,resource_profile_id=profile['resource_profile_id'],
              trial=True,string_entry=None,candidates={},hold_chains={imports[0]['id']:[m['id'] for m in imports]},moves=imports))
        print(boss, 'matched', len(imports), 'actions; voices', [len(m['voices']) for m in imports])
    for move in catalogue['moves']:
        if move['implementation'].get('engine_profile')=='recorded_grounded_trial': move.setdefault('default_binding',None)
    write(ROOT/'data/moves.json',catalogue)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path)
    compile_sources(parser.parse_args().archive)
