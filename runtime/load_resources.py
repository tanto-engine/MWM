# Resolve and retain the installed game resources needed by reviewed imported moves.
# Product definitions supply identities; source bytes and ownership checks remain authoritative.
# See CODE_GUIDE.md for the player-readable flow and terminology.
import hashlib
import json
import mmap
import os
from pathlib import Path
import shutil
import struct
import time
from argparse import Namespace
from ctypes import wintypes as W

import native_loader as loader
from engine_config import atomic_json, read_json
from resource_assets import read_asset

from project_paths import DATA
STATE = struct.Struct('<IIiiQ32s4QII2Q4Q')
loader.K.OpenFileMappingW.argtypes = [W.DWORD, W.BOOL, W.LPCWSTR]
loader.K.OpenFileMappingW.restype = W.HANDLE


class ResourceLoadError(OSError):
    """A native load failed or stayed pending; stop this activation instead of stacking retries."""


def detach_resources(handle, args, module):
    # A queued archive read no longer needs the temporary player-frame hook.
    # Stop new entries, then allow already-entered frame callbacks a bounded drain.
    # Keep the DLL and resource callbacks alive; their pending I/O still owns them.
    detach = loader.remote_export(handle, module, 'NiohResourcesDetach')
    deadline = time.monotonic() + 2
    while True:
        code = loader.call_export(handle, args, detach)
        if not code:
            return
        if code != 170 or time.monotonic() >= deadline:
            raise ResourceLoadError(f'Resource frame hook did not finish detaching: {code}. Restart Nioh before another activation.')
        time.sleep(.01)


def resource_identity(profile, motion_keys=()):
    # Bind one retained native owner to the profile, archive assets and selected motion keys.
    # Hash stable source identities and content fingerprints while excluding editorial notes.
    # Different bosses or revised assets must never share mutable module-local resource state.
    assets = [{key: profile['assets'][kind][key] for key in ('archive', 'entry_id', 'source_name', 'size', 'sha256')}
              for kind in ('actions', 'timing', 'motion', 'camera')]
    identity = [profile['resource_profile_id'], profile['build_sha256'], assets, list(motion_keys),
                sorted(profile.get('object_keys', []))]
    return hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode()).digest()


def load_resources(game, profile_path=DATA/'resources/okatsu.json', motion_keys=()):
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
    motion_keys=sorted(set(motion_keys))
    if len(motion_keys)>32 or any(type(key) is not int or not 0<=key<2**31 for key in motion_keys):
        raise ValueError('Resource motion selection exceeds the reviewed import table')
    object_keys = profile.get('object_keys', [])
    if (not isinstance(object_keys, list) or len(object_keys)>4
            or any(type(key) is not int or not 0<=key<0x149A for key in object_keys)
            or len(set(object_keys))!=len(object_keys)):
        raise ValueError('Object assets must be distinct keys from the supported native factory table')
    object_keys = sorted(object_keys)
    identity = resource_identity(profile, motion_keys)
    tag = identity.hex()
    state = Path(os.environ.get('NIOH_RUNTIME_HOME', Path(__file__).parent))
    code = Path(os.environ.get('TANTO_RUNTIME_CODE', Path(__file__).parent))
    owner_file = state / 'resource-owners' / f'{tag}.json'
    owner = read_json(owner_file)
    if (owner and owner['session'] == game.identity and owner.get('resource_schema') == 9
            and owner['resource_identity'] == tag):
        dll = Path(owner['dll'])
    else:
        source = code / 'native/build/nioh_resources.dll'
        digest = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
        dll = state / 'sessions/runtime' / f'resources_{digest}_{tag}.dll'
        dll.parent.mkdir(parents=True, exist_ok=True)
        if not dll.exists():
            shutil.copy2(source, dll)
        elif dll.read_bytes() != source.read_bytes():
            raise ValueError('Resource DLL identity collision')
    args = Namespace(pid=pid, creation_filetime=birth, harness=False, timeout_ms=10000)
    payload = struct.pack('<4IQ32s4Q', 0x3152504e, 5, pid, 4, birth, identity, *(a['size'] for a in assets))
    for asset in assets:
        # FD3FD0 prepends the archive-root slash before lookup.
        name = asset['source_name'].removeprefix('/').encode('ascii')
        if len(name) >= 80:
            raise ValueError('Archive identifier exceeds native request size')
        payload += name.ljust(80, b'\0')
    payload += struct.pack('<34I',len(motion_keys),*motion_keys,*([0]*(32-len(motion_keys))),0)
    payload += struct.pack('<6I',len(object_keys),*object_keys,*([0]*(4-len(object_keys))),0)
    handle = loader.checked(loader.K.OpenProcess(0x143A, False, pid), 'OpenProcess(resource_loader)')
    started = detached = False
    try:
        loader.validate_target(handle, args)
        module = loader.module_at_path(pid, dll) or loader.load_dll(handle, args, dll)
        atomic_json(owner_file, dict(session=game.identity, dll=str(dll.resolve()), resource_schema=9,
                                    resource_identity=tag, resource_profile_id=profile['resource_profile_id'],
                                    motion_keys=motion_keys, object_keys=object_keys))
        start = loader.remote_export(handle, module, 'NiohResourcesStart')
        started = True
        code = loader.call_export(handle, args, start, payload)
        if code:
            raise ResourceLoadError(f'Resource request rejected: {code}')
        with mmap.mmap(-1, STATE.size, tagname=f'Local\\NiohResources_v9_{pid}_{tag}', access=mmap.ACCESS_READ) as status:
            deadline = time.monotonic() + 30
            while True:
                magic, version, phase, error, observed_birth, observed_identity, actions, timing, motion, camera, completed, thread, player, owner, *object_assets = STATE.unpack(status[:])
                if (magic, version, observed_birth, observed_identity) != (0x3152504e, 5, birth, identity):
                    raise ValueError('Resource owner identity mismatch')
                if not game.alive():
                    raise ResourceLoadError('Nioh exited during move-resource loading. Activation stopped; reopen Nioh and explicitly enable the mod again.')
                if not detached and phase >= 2 and (player or error):
                    detach_resources(handle, args, module)
                    detached = True
                if phase >= 3 and (player or error):
                    if error or phase != 3 or completed != 15:
                        detail=f'clip index {error&0x1fffffff}' if error&0x20000000 else f'error {error}'
                        raise ResourceLoadError(f"{profile['boss_id']}: native resource decode failed ({detail}, completed={completed}, motions={motion_keys})")
                    # E84E60 reads asset+0x160: native decoding must finish before the action can
                    # instantiate its model or projectile. The frame hook is already detached.
                    pending_objects = [str(key) for key, address in zip(object_keys, object_assets)
                                       if not address or game.bytes(address+0x160, 1) != b'\x01']
                    if not pending_objects:
                        return actions, timing, motion, camera, player, owner
                if time.monotonic() >= deadline:
                    if phase == 2:
                        pending = ', '.join(kind for index, kind in enumerate(('actions', 'timing', 'motion', 'camera')) if not completed & (1 << index))
                        raise ResourceLoadError(f"{profile['boss_id'].replace('_', ' ').title()}: archive loading stalled; waiting for {pending}. Activation stopped; restart Nioh before retrying.")
                    if phase == 3 and player:
                        raise ResourceLoadError(f"{profile['boss_id']}: waiting for object assets {', '.join(pending_objects)}. Activation stopped.")
                    raise TimeoutError(f'Waiting for the current player (phase={phase}, completed={completed})')
                time.sleep(.05)
    finally:
        try:
            if started and not detached and game.alive():
                detach_resources(handle, args, module)
        finally:
            loader.K.CloseHandle(handle)
