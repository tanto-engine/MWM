# Historical capture values supply realistic record shapes. Resource handles below
# are owned fixture addresses; no source actor is available to these checks.
import copy
import json
from pathlib import Path
from move_imports import read_import_manifest

ROOT = Path(__file__).resolve().parents[2]
MOD_ROOT = ROOT.parent/'MWM'
FIXTURES = ROOT / 'tests/native/fixtures'
PROFILE = json.loads((FIXTURES / 'session-profile.json').read_text())
BOSS = json.loads((FIXTURES / 'boss-session.json').read_text())
PROFILE['source']['action_resource'] = '0x51000000'
PROFILE['source']['timing_resource'] = '0x52000000'
PROFILE['source'].pop('actor')
PROFILE['source'].pop('owner')
PROFILE['resource_ownership'] = 'engine_retained'
PROFILE['source_actor_required'] = False
BOSS['source_action_resource'] = 0x51000000
BOSS['source_timing_resource'] = 0x52000000
BOSS.update(source_camera_bank=0x53000000, player_camera_slot=0x54000008, camera_original=0x55000000)
PROFILE['camera'] = dict(source_bank=hex(BOSS['source_camera_bank']),
                        player_slot=hex(BOSS['player_camera_slot']), original=hex(BOSS['camera_original']),
                        source_clip='0x56000000')
for name in ('source_actor', 'source_owner', 'source_motion', 'source_timing'):
    BOSS.pop(name)

manifest = read_import_manifest(MOD_ROOT/'data/imports/okatsu.json')
BOSS['imports'] = manifest['moves']
BOSS['string_variant'] = manifest['string_variant']
BOSS['adapters'] = [None] * len(BOSS['imports'])
BOSS.update(hold_variant=0,hold_milliseconds=0,hold_camera_bank=0)
for index, move in enumerate(BOSS['imports']):
    if index < 2:
        prefix = 'source' if index == 0 else 'charge'
        move.update({field:BOSS[prefix+'_'+field] for field in ('descriptor','payload','clip','timing_record')})
    else:
        move.update({field:0x60000000+index*0x10000+offset for field,offset in (
            ('descriptor',0),('payload',0x100),('clip',0x400),('timing_record',0x800))})
PROFILE['imports'] = copy.deepcopy(BOSS['imports'])
PROFILE['string_variant'] = BOSS['string_variant']
PROFILE['adapters'] = copy.deepcopy(BOSS['adapters'])
PROFILE.update(hold_variant=0,hold_milliseconds=0,hold_camera_bank=0,native_grapple=False)
BOSS['native_grapple'] = False
