# Offline invariants and live acceptance have different evidence. A successful
# simulated dispatch must never turn an unverified gameplay feature into "ready".
# TODO: Record current-build evidence for shrine/menu/pause/cutscene recovery,
# death/retry, mission and equipment changes, R1 Ki Pulse, player damage and
# Ki damage/consumption, audible William vocals and startup responsiveness.
# The two test entrypoints are this workflow and test_resource_crashes.py.
# Support cases and disposable native harnesses belong to those entrypoints.
# Exit 0 means the requested mode passed, 1 means an offline failure, and 2
# means gameplay acceptance is incomplete; --offline never implies readiness.
import argparse
import copy
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MOD_ROOT = ROOT.parent/'MWM'
SUPPORT = ROOT/'tests/support'
sys.path[:0] = [str(ROOT), str(SUPPORT), str(ROOT/'runtime'), str(ROOT.parent/'tanto-recorder/src')]
from catalogue import load_catalogue, save_catalogue, merge_recording
from encounter_recording import reconstruct_capture
from engine_config import DEFAULT_PRESET, binding_for_preset
from gestures import ControllerGesture
from run_dispatch import CommandMap
from runtime_session import encode_session, SESSION_CONFIG
from encounter_recording_cases import state, metadata
from session_fixture import PROFILE, BOSS

REQUIRED = ('player_use', 'movement', 'lock_on', 'stance_retention', 'followups', 'interruptions',
            'damage_ownership', 'damage', 'ki_damage', 'ki_consumption', 'ki_pulse',
            'boss_voice_removed', 'william_voice', 'combat_effects', 'cold_launch_resources',
            'menus', 'cutscenes', 'death_retry', 'mission_reload', 'equipment_changes', 'startup')


def move_fingerprint(move):
    # Bind acceptance evidence to the move's gameplay configuration.
    # Hash stable identity, source, binding, adaptation and engine profile in canonical JSON.
    # A receipt for an older configuration cannot certify the newly configured move.
    configuration = {key:move[key] for key in ('id','source','default_binding','adaptation','resource_profile_id')}
    configuration['engine_profile'] = move['implementation']['engine_profile']
    return hashlib.sha256(json.dumps(configuration,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def runtime_fingerprint():
    # Bind acceptance evidence to both required runtime DLLs.
    # Hash their filenames and bytes, returning no identity if either component is absent.
    # Offline tests must not imply acceptance for a missing or different executable build.
    digest = hashlib.sha256()
    for name in ('nioh_skill_runtime.dll','nioh_resources.dll'):
        path = ROOT/'runtime/native/build'/name
        if not path.is_file():
            return None
        digest.update(name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def acceptance_gaps(move, receipt, game_hash, runtime_hash):
    # Identify missing or stale current-build gameplay evidence.
    # Compare move, game, runtime and configuration hashes before checking feature receipts.
    # Passing simulation or an unchecked observation must never mark a move ready for players.
    if receipt is None:
        return ['current-build acceptance evidence'] + [
            feature for feature in REQUIRED if move['verification'].get(feature) != 'confirmed']
    gaps = []
    for key, expected in (('move_id',move['id']), ('game_sha256',game_hash),
                          ('runtime_sha256',runtime_hash), ('configuration_sha256',move_fingerprint(move))):
        if expected is None or receipt.get(key) != expected:
            gaps.append(key)
    for feature in REQUIRED:
        check = receipt.get('checks',{}).get(feature)
        if not isinstance(check,dict) or check.get('passed') is not True:
            gaps.append(feature)
            continue
        reference = check.get('evidence')
        if not isinstance(reference,str):
            gaps.append(feature + ' evidence')
            continue
        evidence = (ROOT/reference).resolve()
        if (not evidence.is_relative_to(ROOT) or not evidence.is_file()
                or hashlib.sha256(evidence.read_bytes()).hexdigest() != check.get('sha256')):
            gaps.append(feature + ' evidence')
    return gaps


class MoveWorkflow(unittest.TestCase):
    def test_record_catalogue_bind_encode_and_publish_both_moves(self):
        # Exercise the complete recorded-move to published-command contract.
        # Reconstruct evidence, merge the catalogue, choose each baseline move and inspect published ABI bytes.
        # The workflow must preserve move identity and binding through every offline stage.
        catalogue = load_catalogue()
        baseline = {move['id']:copy.deepcopy(move) for move in catalogue['moves'] if move['implementation']['selectable']}
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            events = [{'kind':'session'}, state(.1), metadata(t=.15),
                      state(.2,0xC66), metadata(0xC66,1230,t=.25), {'kind':'end'}]
            capture = folder/'events.jsonl'
            capture.write_text('\n'.join(map(json.dumps,events)))
            summary = folder/'reconstruction.json'
            reconstruct_capture(capture,'okatsu',summary)
            target = folder/'moves.json'
            save_catalogue(target, catalogue)
            merged = merge_recording(target,summary)
        for move in merged['moves']:
            if move['id'] in baseline:
                # Better decoding may add source facts; established identities and adaptations stay fixed.
                for key,value in baseline[move['id']]['source'].items():
                    self.assertEqual(move['source'][key],value)
                for key in ('default_binding','adaptation','implementation'):
                    self.assertEqual(move[key],baseline[move['id']][key])
        calibration = json.loads((MOD_ROOT/'data/controller-calibration.json').read_text())
        preset=dict(DEFAULT_PRESET,hold_move='okatsu.leaping_slash')
        binding = binding_for_preset(calibration,preset)
        session = copy.deepcopy(BOSS)
        session['config_tag'] = '123456789abcdef0'
        encoded = encode_session(session,session['session']['pid'],int(session['session']['creation_filetime']))
        self.assertEqual(SESSION_CONFIG.unpack(encoded)[2],SESSION_CONFIG.size)
        config = dict(generation=7,player=session['player'],owner=session['player_owner'],vtable=session['vtable'],
                      banks=[int(address,0) for address in PROFILE['player']['action_banks']],
                      descriptor=session['source_descriptor'],payload=session['source_payload'],key=0xC64,motion=1220,
                      charged=dict(descriptor=session['charge_descriptor'],payload=session['charge_payload'],key=0xC66,motion=1230))
        for hold, move_id in ((False,preset['tap_move']),(True,preset['hold_move'])):
            gate = ControllerGesture(calibration,binding,1000)
            device = calibration['device']
            gate.process(dict(kind='input_device',**device),100)
            for buttons, now in ((0,101),(20,200)):
                gate.process(dict(kind='input',backend=device['backend'],slot=device['slot'],buttons=buttons),now)
            if not hold:
                gate.process(dict(kind='input',backend=device['backend'],slot=device['slot'],buttons=16),249)
            fields = gate.fields(450 if hold else 250)
            self.assertTrue(fields['armed'])
            owned = C.create_string_buffer(224)
            command = CommandMap.__new__(CommandMap)
            command.address,command.sequence = C.addressof(owned),0
            command.publish(config,**fields)
            source = baseline[move_id]['source']
            self.assertEqual(struct.unpack_from('<Ii',owned.raw,64+112),(source['action_id'],source['motion_id']))
            self.assertEqual(struct.unpack_from('<q',owned.raw,64)[0],struct.unpack_from('<q',owned.raw,64+152)[0])

    def test_offline_success_and_partial_observation_never_imply_acceptance(self):
        # Keep offline success separate from current-build gameplay acceptance.
        # Evaluate missing receipts, incomplete feature evidence and a stale configuration hash.
        # Simulation success cannot certify damage, Ki Pulse or lifecycle behavior that was never observed.
        move = load_catalogue()['moves'][0]
        self.assertTrue(acceptance_gaps(move,None,'game','runtime'))
        observed = {'move_id':move['id'],'game_sha256':'game','runtime_sha256':'runtime',
                    'configuration_sha256':move_fingerprint(move),
                    'checks':{'ki_pulse':{'passed':True}}}
        gaps = acceptance_gaps(move,observed,'game','runtime')
        self.assertIn('ki_pulse evidence',gaps)
        self.assertIn('damage',gaps)
        self.assertIn('death_retry',gaps)
        self.assertIn('configuration_sha256',acceptance_gaps(move,dict(observed,configuration_sha256='stale'),'game','runtime'))


class NativeGameplayInvariants(unittest.TestCase):
    def test_owned_memory_harnesses(self):
        # Run native failure checks in disposable owned-memory processes.
        # Compile each native invariant harness with warnings as errors and run it in a disposable process.
        # ABI, recovery and ownership failures must be caught without injecting code into Nioh.
        from run_dispatch_cases import CONFIG
        with tempfile.TemporaryDirectory(prefix='nioh-native-checks-') as temporary:
            folder = Path(temporary)
            owned = C.create_string_buffer(224)
            command = CommandMap.__new__(CommandMap)
            command.address,command.sequence = C.addressof(owned),0
            command.publish(CONFIG,heartbeat=1000,edge=900,expires=2100,chord_sequence=1,armed=True,held=True)
            payload = folder/'command.bin'
            payload.write_bytes(owned.raw[64:])
            for source in sorted((ROOT/'tests/native').glob('*_cases.cpp')):
                with self.subTest(harness=source.stem):
                    binary = folder/(source.stem+'.exe')
                    build = subprocess.run([os.environ.get('CXX','g++'),'-std=c++17','-O2','-Wall','-Wextra','-Werror',
                                            str(source),'-I',str(ROOT/'third_party/minhook/include'),'-o',str(binary)],
                                           capture_output=True,text=True,timeout=60)
                    self.assertEqual(build.returncode,0,build.stdout+build.stderr)
                    arguments = [str(binary)] + ([str(payload)] if source.stem=='publisher_protocol_cases' else [])
                    result = subprocess.run(arguments,capture_output=True,text=True,timeout=30)
                    self.assertEqual(result.returncode,0,result.stdout+result.stderr)


def load_tests(loader, tests, pattern):
    # Expose all support cases through the single move-readiness entrypoint.
    # Add unittest discovery of *_cases.py to this module's workflow checks.
    # Support files retain focused coverage without becoming separate maintained test commands.
    tests.addTests(loader.discover(str(SUPPORT),pattern='*_cases.py'))
    # Product-owned expectations live with MWM, but still run through this single entrypoint.
    import importlib.util
    for path in sorted((ROOT.parent/'MWM/tests').glob('*_cases.py')):
        spec = importlib.util.spec_from_file_location('mwm_'+path.stem, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        tests.addTests(loader.loadTestsFromModule(module))
    return tests


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Check the move workflow and require separate gameplay acceptance.')
    parser.add_argument('--offline',action='store_true',help='Run simulated checks without claiming gameplay readiness.')
    parser.add_argument('--acceptance',type=Path,help='JSON map of move IDs to current-build gameplay receipts.')
    parser.add_argument('--move',action='append',help='Catalogue move ID; defaults to enabled moves.')
    args = parser.parse_args()
    outcome = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    if not outcome.wasSuccessful():
        raise SystemExit(1)
    if args.offline:
        print('Offline checks passed. Gameplay readiness was not assessed.')
        raise SystemExit(0)
    catalogue = load_catalogue()
    selected = args.move or [move['id'] for move in catalogue['moves'] if move['implementation']['selectable']]
    receipts = json.loads(args.acceptance.read_text()) if args.acceptance else {}
    pending = False
    for move_id in selected:
        move = next(move for move in catalogue['moves'] if move['id']==move_id)
        gaps = acceptance_gaps(move,receipts.get(move_id),catalogue['supported_build_sha256'],runtime_fingerprint())
        print(move['name'] + (': NOT READY — ' + ', '.join(gaps) if gaps else ': gameplay acceptance complete'))
        pending |= bool(gaps)
    raise SystemExit(2 if pending else 0)
