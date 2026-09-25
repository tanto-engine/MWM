import hashlib
import json
import mmap
from pathlib import Path
import shutil
import struct
import time
from argparse import Namespace
from ctypes import wintypes as W

import native_loader as loader
from engine_config import atomic_json, read_json
from resource_assets import read_asset

ROOT = Path(__file__).resolve().parents[1]
STATE = struct.Struct('<IIiiQ32s4QII2Q')
loader.K.OpenFileMappingW.argtypes = [W.DWORD, W.BOOL, W.LPCWSTR]
loader.K.OpenFileMappingW.restype = W.HANDLE


def resource_identity(profile):
    # Bind one retained native owner to the profile and exact ordered archive assets.
    # Hash stable source identities and content fingerprints while excluding editorial notes.
    # Different bosses or revised assets must never share mutable module-local resource state.
    assets = [{key: profile['assets'][kind][key] for key in ('archive', 'entry_id', 'source_name', 'size', 'sha256')}
              for kind in ('actions', 'timing', 'motion', 'camera')]
    identity = [profile['resource_profile_id'], profile['build_sha256'], assets]
    return hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode()).digest()


def load_resources(game, profile_path=ROOT / 'catalogue/resource_profiles/okatsu.json'):
    # Request engine-owned action, motion, timing and camera resources.
    # Validate archive assets, reuse their immutable profile owner and poll its native phase.
    # No source boss pointer is needed, and incomplete loads remain explicit.
    profile = json.loads(profile_path.read_text())
    if profile['build_sha256'] != game.identity['build_sha256']:
        raise ValueError('Resource profile targets a different game build')
    assets = [profile['assets'][kind] for kind in ('actions', 'timing', 'motion', 'camera')]
    for asset in assets:
        read_asset(loader.NIOH.parent / 'archive', asset)
    pid = game.identity['pid']
    birth = int(game.identity['creation_filetime'])
    identity = resource_identity(profile)
    tag = identity.hex()
    owner_file = Path(__file__).parent / 'resource-owners' / f'{tag}.json'
    owner = read_json(owner_file)
    if (owner and owner['session'] == game.identity and owner.get('resource_schema') == 5
            and owner['resource_identity'] == tag):
        dll = Path(owner['dll'])
    else:
        source = Path(__file__).parent / 'native/build/nioh_resources.dll'
        digest = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
        dll = Path(__file__).parent / 'sessions/runtime' / f'resources_{digest}_{tag}.dll'
        dll.parent.mkdir(parents=True, exist_ok=True)
        if not dll.exists():
            shutil.copy2(source, dll)
        elif dll.read_bytes() != source.read_bytes():
            raise ValueError('Resource DLL identity collision')
    args = Namespace(pid=pid, creation_filetime=birth, harness=False, timeout_ms=10000)
    payload = struct.pack('<4IQ32s4Q', 0x3152504e, 3, pid, 4, birth, identity, *(a['size'] for a in assets))
    for asset in assets:
        # FD3FD0 prepends the archive-root slash before lookup.
        name = asset['source_name'].removeprefix('/').encode('ascii')
        if len(name) >= 80:
            raise ValueError('Archive identifier exceeds native request size')
        payload += name.ljust(80, b'\0')
    handle = loader.checked(loader.K.OpenProcess(0x143A, False, pid), 'OpenProcess(resource_loader)')
    try:
        loader.validate_target(handle, args)
        module = loader.module_at_path(pid, dll) or loader.load_dll(handle, args, dll)
        atomic_json(owner_file, dict(session=game.identity, dll=str(dll.resolve()), resource_schema=5,
                                    resource_identity=tag, resource_profile_id=profile['resource_profile_id']))
        start = loader.remote_export(handle, module, 'NiohResourcesStart')
        code = loader.call_export(handle, args, start, payload)
        if code:
            raise OSError(f'Resource request rejected: {code}')
        with mmap.mmap(-1, STATE.size, tagname=f'Local\\NiohResources_v5_{pid}_{tag}', access=mmap.ACCESS_READ) as status:
            deadline = time.monotonic() + 30
            while True:
                magic, version, phase, error, observed_birth, observed_identity, actions, timing, motion, camera, completed, thread, player, owner = STATE.unpack(status[:])
                if (magic, version, observed_birth, observed_identity) != (0x3152504e, 3, birth, identity):
                    raise ValueError('Resource owner identity mismatch')
                if phase >= 3 and (player or error):
                    detach = loader.remote_export(handle, module, 'NiohResourcesDetach')
                    code = loader.call_export(handle, args, detach)
                    if code == 170:
                        time.sleep(.01)
                        continue
                    if code:
                        raise OSError(f'Resource frame hook did not detach: {code}')
                    if error or phase != 3 or completed != 15:
                        raise OSError(f'Native resource decode failed: {error}, completed={completed}')
                    return actions, timing, motion, camera, player, owner
                if not game.alive() or time.monotonic() >= deadline:
                    raise TimeoutError(f'Resource loading pending (phase={phase}, completed={completed}); retained request for retry')
                time.sleep(.05)
    finally:
        loader.K.CloseHandle(handle)
