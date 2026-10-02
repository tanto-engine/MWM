# Run the real package boundary/decoder loop in a disposable process. An access
# violation is a failed test, never a reason to try the same build inside Nioh.
import json
import argparse
import contextlib
import ctypes as C
from ctypes import wintypes as W
import io
import os
from pathlib import Path
import subprocess
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
MOD_ROOT = ROOT/'mwm'
sys.path.insert(0, str(ROOT / 'runtime'))
from resource_assets import read_asset
from native_loader import NIOH
import engine_config
import supervisor
import load_resources as resources

HARNESS = r'''
#include <cassert>
#include <fstream>
#include <iterator>
#include <vector>
#include "motion_package.h"
static uint32_t calls, fail_at;
static uintptr_t clip_storage[32768][8];
static void* make_clip(const uint8_t*, uint32_t, void*) {
    // Simulate the clip factory exhausting memory at one selected allocation.
    // Return owned storage for earlier clips and null at the requested index.
    // The decoder must stop without dereferencing or publishing the failed clip.
    const auto index = calls++;
    return index == fail_at ? nullptr : clip_storage[index];
}
static void put(std::vector<uint8_t>& b, size_t at, uint32_t value) {
    // Corrupt one 32-bit field in a copied resource package.
    // Copy bytes directly so unaligned file offsets remain valid fixture writes.
    // Each rejection case changes only the boundary field under investigation.
    memcpy(b.data()+at,&value,4);
}
int main(int argc, char** argv) {
    // Exercise a real package in an isolated process with owned clip storage.
    // Exhaust every allocation position, then corrupt its counts and table bounds.
    // Invalid resources must fail before any unsafe decoder callback or publication.
    assert(argc == 2);
    std::ifstream file(argv[1], std::ios::binary);
    std::vector<uint8_t> pack((std::istreambuf_iterator<char>(file)), {});
    assert(motion_package_bounds(pack.data(), pack.size()));
    const uint32_t count = package_u32(pack.data(),20);
    std::vector<uintptr_t> output(count+2,0);
    uint32_t failed=0;
    // Exhaust the allocator at every clip, including after partial publication.
    // The game crashed because its bulk decoder dereferenced a null factory result.
    for (fail_at=0; fail_at<count; ++fail_at) {
        std::fill(output.begin(),output.end(),0);
        output.front()=0xabc; output.back()=0xdef; calls=0;
        assert(!decode_motion_clips(pack.data(),pack.size(),nullptr,make_clip,output.data()+1,count,failed));
        assert(failed==fail_at && calls==fail_at+1);
        assert(!output[failed+1] && output.front()==0xabc && output.back()==0xdef);
        for (uint32_t i=0;i<fail_at;++i) assert(output[i+1] && reinterpret_cast<uint32_t*>(output[i+1])[9]==1);
    }
    fail_at=UINT32_MAX; calls=0;
    assert(decode_motion_clips(pack.data(),pack.size(),nullptr,make_clip,output.data()+1,count,failed));
    assert(calls==count);
    // A one-clip request must not exhaust the allocator on unrelated animations.
    // Keep the full lookup index while leaving unselected clip slots empty.
    // A missing key rejects before any allocation, rather than yielding a partial package.
    const uint32_t selection_hash=package_u32(pack.data(),40);
    uint32_t selected_key=0,selected_index=UINT32_MAX;
    for(uint32_t row=0;row<package_u32(pack.data(),selection_hash);++row) {
        const auto index=package_u32(pack.data(),selection_hash+12+row*8);
        if(index!=UINT32_MAX && package_u32(pack.data(),package_u32(pack.data(),32)+index*4)) {
            selected_key=package_u32(pack.data(),selection_hash+8+row*8);selected_index=index;break;
        }
    }
    assert(selected_index!=UINT32_MAX);
    std::fill(output.begin(),output.end(),0);calls=0;fail_at=1;
    assert(decode_motion_clips(pack.data(),pack.size(),nullptr,make_clip,output.data()+1,count,failed,&selected_key,1));
    assert(calls==1 && output[selected_index+1]);
    const uint32_t missing_key=0x7ffffffe;calls=0;
    assert(!decode_motion_clips(pack.data(),pack.size(),nullptr,make_clip,output.data()+1,count,failed,&missing_key,1) && calls==0);
    auto empty=pack;
    put(empty,package_u32(pack.data(),32)+selected_index*4,0);
    put(empty,package_u32(pack.data(),36)+selected_index*4,0);
    assert(motion_package_bounds(empty.data(),empty.size())); // Sparse packages are valid, required holes are not.
    std::fill(output.begin(),output.end(),0);calls=0;
    assert(!decode_motion_clips(empty.data(),empty.size(),nullptr,make_clip,output.data()+1,count,failed,&selected_key,1));
    assert(calls==0 && failed==selected_index && !output[selected_index+1]);
    // Reject malformed data before *any* native decoder call.
    const auto reject=[&](const std::vector<uint8_t>& bad, size_t size) {
        // Check malformed package rejection before the clip factory is invoked.
        // Reset the factory count and supply the exact corrupted buffer length.
        // Bounds validation must protect native decoding even when output storage exists.
        calls=0;
        assert(!decode_motion_clips(bad.data(),size,nullptr,make_clip,output.data()+1,count,failed));
        assert(calls==0);
    };
    for (size_t size=0;size<48;++size) reject(pack,size);
    auto bad=pack; put(bad,20,UINT32_MAX); reject(bad,bad.size());
    for (uint32_t field : {32u,36u,40u}) { bad=pack;put(bad,field,UINT32_MAX);reject(bad,bad.size()); }
    const auto offsets=package_u32(pack.data(),32),sizes=package_u32(pack.data(),36),hash=package_u32(pack.data(),40);
    bad=pack;put(bad,offsets,UINT32_MAX-4);reject(bad,bad.size());
    bad=pack;put(bad,sizes,UINT32_MAX);reject(bad,bad.size());
    bad=pack;put(bad,hash,UINT32_MAX);reject(bad,bad.size());
    bad=pack;put(bad,hash+12,count);reject(bad,bad.size());
    bad=pack;put(bad,package_u32(pack.data(),offsets)+24,UINT32_MAX);reject(bad,bad.size());
    bad=pack;bad[package_u32(pack.data(),offsets)]='!';reject(bad,bad.size());
    calls=0;assert(!decode_motion_clips(nullptr,pack.size(),nullptr,make_clip,output.data()+1,count,failed));assert(!calls);
}
'''


class ResourceCrashTests(unittest.TestCase):
    def test_profiles_retain_distinct_native_owners_and_reuse_the_same_identity(self):
        # Load two profiles in one fake process while retaining both native owners.
        # Capture actual DLL paths, mapping names and request bytes through mocked exports.
        # A second boss must never collide with or replace the first boss's retained resources.
        with tempfile.TemporaryDirectory(prefix='nioh-profile-owners-') as folder:
            root = Path(folder)
            build = root / 'native/build'
            build.mkdir(parents=True)
            (build / 'nioh_resources.dll').write_bytes(b'owned test DLL; never loaded')
            object_ready = True
            game = SimpleNamespace(identity=dict(pid=123, creation_filetime='456', build_sha256='build'),
                                   main=dict(path=r'D:\Games\Nioh\nioh.exe'),
                                   alive=lambda: True, bytes=lambda address, count: bytes([object_ready]))
            assets = {kind: dict(archive='archive_00.lnk', entry_id=index, source_name='/'+kind,
                                size=100+index, sha256=str(index)*64)
                      for index,kind in enumerate(('actions','timing','motion','camera'))}
            first = dict(resource_profile_id='first.resources.v1', boss_id='first', build_sha256='build', assets=assets)
            second = dict(first, resource_profile_id='second.resources.v1', object_keys=[3257,3258])
            paths = [root/'first.json', root/'second.json']
            for path, profile in zip(paths, (first, second)):
                path.write_text(json.dumps(profile))
            # An older loader must not bypass new transition guards through its saved owner path.
            # Keep the old DLL allocated; select this build's owner for the next activation.
            stale_path=root/'old-resource-owner.dll'
            owner_path=root/'resource-owners'/(resources.resource_identity(first).hex()+'.json')
            owner_path.parent.mkdir()
            owner_path.write_text(json.dumps(dict(session=game.identity,resource_schema=8,
                resource_identity=resources.resource_identity(first).hex(),dll=str(stale_path))))
            loaded, mappings, requests = [], [], []
            corrupt_identity = False
            phase, detaches = 3, []
            def module_at_path(pid, dll):
                # Resolve only the fake modules already loaded through this fixture.
                # Match their complete immutable path without opening a process.
                # A repeated profile should reuse its retained module instead of loading another copy.
                return {'path':str(dll)} if str(dll) in loaded else None
            def load_module(handle, args, dll):
                # Retain one simulated module for each requested DLL path.
                # Return only module metadata and execute no binary code.
                # Distinct resource profiles require distinct module-local ownership state.
                loaded.append(str(dll))
                return {'path':str(dll)}
            def export(handle, args, address, payload=None):
                # Capture each Start request while acknowledging both export stages.
                # Preserve the request bytes for the mapping fixture and identity assertions.
                # Resource ownership is verified at the caller boundary without remote writes.
                if payload is not None: requests.append(payload)
                else: detaches.append(True)
                return 0
            def status_mapping(fileno, length, tagname, access):
                # Publish completed owned resources for the most recent Start request.
                # Echo its process birth and profile identity in a disposable local byte stream.
                # The caller must verify the echoed identity before accepting any pointer values.
                mappings.append(tagname)
                self.assertEqual(length, 144)
                self.assertEqual(len(requests[-1]), 568)
                identity = bytes(32) if corrupt_identity else requests[-1][24:56]
                object_count = struct.unpack_from('<I', requests[-1], 544)[0]
                objects = [0x10000+i*4096 if i<object_count else 0 for i in range(4)]
                return StatusView(resources.STATE.pack(0x3152504e, 5, phase, 0, 456, identity,
                                                       1, 2, 3, 4, 15 if phase == 3 else 1, 1, 5, 6, *objects))
            class StatusView(io.BytesIO):
                def __getitem__(self, key):
                    # Expose the slice-reading interface used by a read-only mmap.
                    # Return bytes from the in-memory status stream without moving its cursor.
                    # The loader can consume the fixture with its unchanged mapping protocol.
                    return self.getvalue()[key]
            with patch.object(resources, '__file__', str(root/'load_resources.py')), \
                 patch.object(resources, 'read_asset', return_value=b'fixture'), \
                 patch.object(resources.loader.K, 'OpenProcess', return_value=1), \
                 patch.object(resources.loader.K, 'CloseHandle'), \
                 patch.object(resources.loader, 'validate_target'), \
                 patch.object(resources.loader, 'module_at_path', side_effect=module_at_path), \
                 patch.object(resources.loader, 'load_dll', side_effect=load_module), \
                 patch.object(resources.loader, 'remote_export', return_value=1), \
                 patch.object(resources.loader, 'call_export', side_effect=export), \
                 patch.object(resources.mmap, 'mmap', side_effect=status_mapping):
                for path in (paths[0], paths[1], paths[0]):
                    self.assertEqual(resources.load_resources(game, path), (1,2,3,4,5,6))
                corrupt_identity = True
                with self.assertRaisesRegex(ValueError, 'Resource owner identity mismatch'):
                    resources.load_resources(game, paths[0])
                self.assertEqual(len(detaches), 4, 'Identity errors must also release the temporary hook')
                corrupt_identity, phase = False, 2
                with patch.object(resources.time, 'monotonic', side_effect=[0, 0, 31]):
                    with self.assertRaisesRegex(resources.ResourceLoadError, 'waiting for timing, motion, camera'):
                        resources.load_resources(game, paths[0])
                self.assertEqual(len(detaches), 5, 'Pending I/O must release the frame hook once before timeout')
                # Finished animations are insufficient while a required model/projectile is pending.
                # Abort without reattaching the frame hook or reporting a usable move.
                # A later completed dependency still reuses the same retained native owner.
                phase, object_ready = 3, False
                with patch.object(resources.time, 'monotonic', side_effect=[0, 0, 31]):
                    with self.assertRaisesRegex(resources.ResourceLoadError, 'object assets 3257, 3258'):
                        resources.load_resources(game, paths[1])
                self.assertEqual(len(detaches), 6)
                object_ready = True
                self.assertEqual(resources.load_resources(game, paths[1]), (1,2,3,4,5,6))
                self.assertEqual(struct.unpack_from('<6I', requests[-1], 544), (2,3257,3258,0,0,0))
            self.assertNotEqual(loaded[0],str(stale_path),'Older loader bypassed current transition guards')
            self.assertEqual(json.loads(owner_path.read_text())['resource_schema'],9)
            self.assertTrue(all('NiohResources_v9_' in name for name in mappings))
            self.assertEqual(len(loaded), 2, 'Different profiles reused one native DLL owner')
            self.assertNotEqual(mappings[0], mappings[1])
            self.assertEqual(mappings[0], mappings[2])
            self.assertEqual(requests[0], requests[2])
            self.assertNotEqual(requests[0], requests[1])
            for path, request in zip(loaded, requests):
                self.assertIn(request[24:56].hex(), Path(path).name)

    def test_resource_identity_tracks_asset_changes_without_editorial_churn(self):
        # Bind owner identity to the exact resource content and source profile.
        # Change every stable asset field independently while leaving editorial notes variable.
        # Revised assets require a new native owner, but documentation edits must reuse loaded objects.
        profile = json.loads((MOD_ROOT/'data/resources/okatsu.json').read_text())
        identity = resources.resource_identity(profile)
        self.assertNotEqual(resources.resource_identity(profile, [1220]), identity)
        # A model/projectile dependency must invalidate an animation-only cached owner.
        self.assertNotEqual(resources.resource_identity(dict(profile, object_keys=[3257,3258])), identity)
        profile['assets']['actions']['evidence'] = 'Different research wording'
        profile['status'] = 'different editorial status'
        self.assertEqual(resources.resource_identity(profile), identity)
        for field in ('archive', 'entry_id', 'source_name', 'size', 'sha256'):
            changed = json.loads(json.dumps(profile))
            value = changed['assets']['actions'][field]
            changed['assets']['actions'][field] = value + 1 if isinstance(value, int) else value + 'changed'
            self.assertNotEqual(resources.resource_identity(changed), identity, field)

    def test_real_package_exhaustion_and_corruption(self):
        # Reject corrupt real packages and every clip-allocation failure without crashing.
        # Decode the actual motion and camera archives while exhausting every allocation position.
        # Malformed bounds or partial construction must fail before a native access violation.
        manifest = json.loads((MOD_ROOT / 'data/resources/okatsu.json').read_text())
        with tempfile.TemporaryDirectory(prefix='nioh-crash-check-') as folder:
            folder = Path(folder)
            source, binary, asset = folder/'crash.cpp', folder/'crash.exe', folder/'motion.bin'
            source.write_text(HARNESS)
            subprocess.run(['g++', '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror', str(source),
                            '-I', str(ROOT/'runtime/native'), '-o', str(binary)], check=True)
            for name in ('motion', 'camera'):
                with self.subTest(package=name):
                    asset.write_bytes(read_asset(NIOH.parent / 'archive', manifest['assets'][name]))
                    subprocess.run([str(binary), str(asset)], check=True, timeout=30)


@unittest.skipUnless(os.name == 'nt', 'Windows file sharing')
class StatusSharingTests(unittest.TestCase):
    def test_reader_coexists_with_atomic_replacement_delete_handle(self):
        # Allow status readers to coexist with Windows replacement delete handles.
        # Hold a real Windows DELETE-sharing handle while opening the status reader.
        # The former text reader fails deterministically, while the shared reader must still return complete JSON.
        kernel = C.WinDLL('kernel32', use_last_error=True)
        kernel.CreateFileW.argtypes = [W.LPCWSTR, W.DWORD, W.DWORD, C.c_void_p, W.DWORD, W.DWORD, W.HANDLE]
        kernel.CreateFileW.restype = W.HANDLE
        kernel.CloseHandle.argtypes = [W.HANDLE]
        with tempfile.TemporaryDirectory(prefix='nioh-sharing-') as folder:
            path = Path(folder)/'live.json'
            engine_config.atomic_json(path, {'state':'enabled'})
            # DELETE access (0x10000) with read/write/delete sharing (7)
            # reproduces the handle coexistence required by atomic replacement.
            handle = kernel.CreateFileW(str(path), 0x10000, 7, None, 3, 0x80, None)
            if handle == C.c_void_p(-1).value:
                raise C.WinError(C.get_last_error())
            try:
                # This is the former read_json implementation and reproduces
                # the launcher's PermissionError without a timing-dependent race.
                with self.assertRaises(PermissionError):
                    path.read_text(encoding='utf-8-sig')
                self.assertEqual(engine_config.read_json(path), {'state':'enabled'})
            finally:
                kernel.CloseHandle(handle)

    def test_writer_replaces_file_while_reader_keeps_a_complete_snapshot(self):
        # Keep a complete old snapshot readable while the file is replaced.
        # Replace the status pathname after its old stream has opened.
        # Readers must see one complete generation rather than mixed bytes from both publications.
        with tempfile.TemporaryDirectory(prefix='nioh-sharing-') as folder:
            path = Path(folder)/'live.json'
            before, after = {'state':'enabled', 'sequence':1}, {'state':'suspended', 'sequence':2}
            engine_config.atomic_json(path, before)
            load = json.load
            def replace_before_read(stream):
                # Replace the status path after the reader has opened its stream.
                # Read through that existing stream using the original JSON loader.
                # A shared reader must retain a complete old snapshot across atomic replacement.
                engine_config.atomic_json(path, after)
                return load(stream)
            with patch.object(engine_config.json, 'load', side_effect=replace_before_read):
                self.assertEqual(engine_config.read_json(path), before)
            self.assertEqual(engine_config.read_json(path), after)

    def test_exclusive_access_and_malformed_json_still_fail_loudly(self):
        # Keep access denial and malformed JSON visible to the caller.
        # Provide invalid JSON and a persistently exclusive handle, then check a missing-file default.
        # Retry support must not suppress corruption or denial and must not mutate caller-owned defaults.
        with tempfile.TemporaryDirectory(prefix='nioh-sharing-') as folder:
            path = Path(folder)/'live.json'
            path.write_text('{broken')
            with self.assertRaises(json.JSONDecodeError):
                engine_config.read_json(path, {'state':'enabled'})
            handle = engine_config.kernel.CreateFileW(str(path), 0x80000000, 0, None, 3, 0x80, None)
            if handle == C.c_void_p(-1).value:
                raise C.WinError(C.get_last_error())
            try:
                with self.assertRaises(PermissionError):
                    engine_config.read_json(path, {'state':'enabled'})
            finally:
                engine_config.kernel.CloseHandle(handle)
            missing = Path(folder)/'missing.json'
            default = {'moves':[]}
            result = engine_config.read_json(missing, default)
            result['moves'].append('changed')
            self.assertEqual(default, {'moves':[]})

    def test_reader_retries_only_the_replacement_sharing_window(self):
        # Retry only the bounded Windows replacement sharing window.
        # Release a sharing conflict on the first five-millisecond retry and separately simulate access denied.
        # Only transient replacement conditions may retry; unrelated errors must surface immediately.
        with tempfile.TemporaryDirectory(prefix='nioh-sharing-') as folder:
            path = Path(folder)/'live.json'
            path.write_text('{"state":"enabled"}')
            handle = engine_config.kernel.CreateFileW(str(path), 0x80000000, 0, None, 3, 0x80, None)
            if handle == C.c_void_p(-1).value:
                raise C.WinError(C.get_last_error())
            released = False
            def finish_replacement(seconds):
                # Release the conflicting file handle on the first bounded retry delay.
                # Assert the requested delay is exactly five milliseconds and occurs only once.
                # The reader may recover a replacement race without hiding persistent access denial.
                nonlocal released
                self.assertEqual(seconds, .005)
                self.assertFalse(released)
                engine_config.kernel.CloseHandle(handle)
                released = True
            try:
                with patch.object(engine_config.time, 'sleep', side_effect=finish_replacement):
                    self.assertEqual(engine_config.read_json(path), {'state':'enabled'})
                self.assertTrue(released)
            finally:
                if not released:
                    engine_config.kernel.CloseHandle(handle)
            path.unlink()
            with patch.object(engine_config.time, 'sleep', side_effect=lambda seconds: (
                # Recreate the temporarily missing status path during the retry delay.
                # Write complete JSON before the reader's next open attempt.
                # The missing-name replacement window must recover without using the fallback value.
                path.write_text('{"state":"enabled"}')
            )):
                self.assertEqual(engine_config.read_json(path, {'state':'missing'}), {'state':'enabled'})
            with patch.object(engine_config.kernel, 'CreateFileW', return_value=C.c_void_p(-1).value), \
                 patch.object(engine_config.C, 'get_last_error', return_value=5), \
                 patch.object(engine_config.time, 'sleep') as delay:
                with self.assertRaises(PermissionError):
                    engine_config.read_json(path)
                delay.assert_not_called()


class SupervisorCrashTests(unittest.TestCase):
    def test_unexpected_exit_waits_for_worker_disarm_and_cleanup(self):
        # This worker is a disposable process with no game access. Its completion
        # marker appears only after it observes Stop and finishes its cleanup.
        # Disarm and await worker cleanup when supervisor monitoring fails unexpectedly.
        # Inject read, publication and interruption failures while a disposable child waits for Stop.
        # The supervisor must await its cleanup marker and exit before propagating the original failure.
        worker = '''
from pathlib import Path
import sys, time
trace, stop, cleaned = map(Path, sys.argv[1:])
trace.mkdir()
(trace/'live.json').write_text('{"state":"enabled"}')
(trace/'ready.json').touch()
deadline = time.monotonic()+5
while not stop.exists():
    if time.monotonic() >= deadline:
        raise SystemExit(2)
    time.sleep(.005)
time.sleep(.03)
cleaned.write_text('disarmed and recovered')
'''
        for stage, failure in (('read', PermissionError('injected status read failure')),
                               ('write', OSError('injected status publish failure')),
                               ('interrupt', KeyboardInterrupt())):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory(prefix='nioh-supervisor-') as folder:
                runtime = Path(folder)
                dll, stopped, cleaned = runtime/'fixture.dll', runtime/'stop.flag', runtime/'cleaned.txt'
                dll.write_bytes(b'fixture; never loaded')
                (runtime/'boss-session.json').write_text(json.dumps(
                    {'config_tag':'0123456789abcdef','session':{'pid':123}}))
                children = []
                popen, read, write = subprocess.Popen, engine_config.read_json, engine_config.atomic_json
                def spawn(command, **kwargs):
                    # Replace the real dispatcher command with a disposable cleanup-aware worker.
                    # Reuse its output folder and pass only temporary Stop and completion paths.
                    # Supervisor crash tests must exercise child ownership without injecting gameplay code.
                    trace = command[command.index('--outdir')+1]
                    child = popen([sys.executable, '-c', worker, trace, str(stopped), str(cleaned)], **kwargs)
                    children.append(child)
                    return child
                def read_status(path, default=None):
                    # Inject a monitoring failure only when the worker's live status is read.
                    # Delegate all other status reads to the actual shared-file reader.
                    # Unexpected read errors or interruption must trigger child disarm and awaited cleanup.
                    if Path(path).name == 'live.json' and stage in ('read', 'interrupt'):
                        raise failure
                    return read(path, default)
                def write_status(path, value):
                    # Inject publication failure after the worker reaches enabled state.
                    # Preserve ordinary status writes through the real atomic writer.
                    # A reporting failure must not orphan the still-running gameplay worker.
                    if Path(path).name == 'play-status.json' and value['state'] == 'enabled' and stage == 'write':
                        raise failure
                    write(path, value)
                try:
                    with patch.object(supervisor, 'HERE', runtime), \
                         patch.object(supervisor.subprocess, 'run', return_value=SimpleNamespace(returncode=0)), \
                         patch.object(supervisor.subprocess, 'Popen', side_effect=spawn), \
                         patch.object(supervisor, 'read_json', side_effect=read_status), \
                         patch.object(supervisor, 'atomic_json', side_effect=write_status), \
                         patch.object(supervisor, 'process_identity', return_value={'publisher_pid':12}), \
                         contextlib.redirect_stdout(io.StringIO()):
                        with self.assertRaises(type(failure)) as raised:
                            supervisor.supervise(argparse.Namespace(dll=dll))
                    self.assertIs(raised.exception, failure)
                    self.assertTrue(stopped.exists())
                    self.assertEqual(cleaned.read_text(), 'disarmed and recovered')
                    self.assertEqual(len(children), 1)
                    self.assertEqual(children[0].returncode, 0)
                finally:
                    stopped.touch()
                    for child in children:
                        child.wait(timeout=6)


if __name__ == '__main__':
    unittest.main()
