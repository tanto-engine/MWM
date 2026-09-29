"""MWM product checks, loaded by Engine's maintained offline entrypoint."""
import json
from pathlib import Path
import tempfile
import unittest
import engine_config as config
from runtime_session import encode_session, MOVE_SETTINGS
import runtime_session_cases as sessions
ROOT = Path(__file__).resolve().parents[1]


class SwordConfigurationTests(unittest.TestCase):
    def test_capture_failure_keeps_worker_available(self):
        import subprocess
        import sys
        with tempfile.TemporaryDirectory(prefix='mwm-capture-') as folder:
            requests = '\n'.join(json.dumps(dict(id=index, method=method, params={}))
                                 for index, method in enumerate(('capture_start', 'capture_start', 'test_bad_reply', 'snapshot'), 1)) + '\n'
            result = subprocess.run([sys.executable, '-B', str(ROOT/'tests/desktop_worker_fixture.py'), folder],
                                    input=requests, capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            replies = [json.loads(line) for line in result.stdout.splitlines()]
            self.assertEqual([reply['id'] for reply in replies], [1, 2, 3, 4])
            self.assertIn('Controller listener fixture failure', replies[0]['error']['message'])
            self.assertEqual(replies[1]['result']['status'], 'Press one input')
            self.assertIn('Out of range float values', replies[2]['error']['message'])
            self.assertIn('preset', replies[3]['result'])
            self.assertIn('AssertionError', result.stderr)

    def test_press_to_bind_detects_xinput_without_preselecting_a_mapping(self):
        import importlib.util
        import sys
        from unittest.mock import patch
        sys.path.insert(0, str(ROOT/'app'))
        spec = importlib.util.spec_from_file_location('mwm_capture_review', ROOT/'app/web_worker.py')
        worker = importlib.util.module_from_spec(spec); spec.loader.exec_module(worker)
        calibration = json.loads((ROOT/'data/controller-calibration.json').read_text())
        event = dict(backend='xinput', slot=1)
        class Reader:
            def __init__(self):
                self.events = iter([
                    [dict(event, kind='input_device')],
                    [dict(event, kind='input', buttons=0, axes={'lt': 0, 'rt': 0}, pov=None, edge_basis='unknown')],
                    [dict(event, kind='input', buttons=0x2000, axes={'lt': 0, 'rt': 0}, pov=None, edge_basis='previous_observation')],
                ])
            def poll(self): return next(self.events)
        for running in (False, True):
            with self.subTest(game_running=running), tempfile.TemporaryDirectory() as folder, \
                    patch.object(worker, 'ControllerReader', return_value=Reader()), \
                    patch.object(worker, 'process_matches', return_value=running):
                desktop = worker.Desktop(); desktop.location = lambda: Path(folder)
                desktop.start_capture(calibration)
                desktop.poll_capture(); desktop.poll_capture(); result = desktop.poll_capture()
                self.assertEqual(result['mask'], 0x2000)
                self.assertEqual(result['calibration']['device'], dict(backend='xinput', slot=1))
                preset = json.loads((ROOT/'data/preset.json').read_text())
                remapped = desktop.dispatch('controller', dict(choice='detected', preset=preset,
                    calibration=calibration, detected_calibration=result['calibration']))
                self.assertEqual(remapped['calibration']['controller_slot'], 1)
                self.assertEqual(remapped['preset']['trigger_mask'], 0x400)

    def test_haptic_confirmation_stops_the_selected_xinput_motor(self):
        import importlib.util
        import sys
        from unittest.mock import patch
        sys.path.insert(0, str(ROOT/'app'))
        spec = importlib.util.spec_from_file_location('mwm_haptic_review', ROOT/'app/web_worker.py')
        worker = importlib.util.module_from_spec(spec); spec.loader.exec_module(worker)
        calls = []
        class SetState:
            def __call__(self, slot, pointer):
                calls.append((slot, pointer._obj.left, pointer._obj.right))
                return 0
        class Library:
            XInputSetState = SetState()
        with patch.object(worker.C, 'WinDLL', return_value=Library()), patch.object(worker.time, 'sleep'):
            self.assertFalse(worker.haptic_pulse(None))
            self.assertTrue(worker.haptic_pulse(2))
        self.assertEqual(calls, [(2, 0, 4500), (2, 0, 0)])

    def test_complete_trial_compiles_separate_boss_owners_and_requested_bindings(self):
        # Compile the exact requested trial through the same encoder used to enable gameplay.
        # Colliding Jin/Oda action numbers must remain in separate resource-owner banks.
        # These checks establish routing/identity contracts, not projectile or hitbox acceptance.
        import copy
        from game_controller import game_binding
        preset = config.validate_preset(json.loads((ROOT/'data/presets/sword-rebuild-1.json').read_text(encoding='utf8')))
        self.assertEqual(json.loads((ROOT/'data/preset.json').read_text(encoding='utf8')), preset,
                         'Fresh installs must receive the current Sword Rebuild moveset')
        fixture = sessions.RuntimeSessionTests(); fixture.setUp(); fixture.configured_fixture(preset)
        owners = {}
        for move, adapter in zip(fixture.config['imports'],fixture.config['adapters']):
            if adapter is None: continue
            boss=move['id'].partition('.')[0]
            owners.setdefault(boss,len(owners)+1)
            offset=owners[boss]*0x10000000
            for field in ('action_resource','timing_resource','bank','motion_bank','timing_wrapper'):
                adapter[field]+=offset
            for field in ('descriptor','payload','clip','timing_record'): move[field]+=offset
        self.assertEqual(len(fixture.config['imports']),25)
        self.assertEqual(len(encode_session(fixture.config,fixture.pid,fixture.born)),12416)
        self.assertEqual([b['kind'] for b in fixture.config['skill_bindings']],[1,1,1,5,4])
        self.assertEqual(preset['chord_stance'],'low')
        # The faster Oda root must also reach its second slash through ordinary speed inheritance.
        self.assertEqual([setting['speed'] for move,setting in zip(fixture.config['imports'],fixture.config['move_settings'])
                          if move['id'].startswith('oda_nobunaga.')], [1.1, 1.1])
        calibration=json.loads((ROOT/'data/controller-calibration.json').read_text())
        _, binding=game_binding(calibration,config.binding_for_preset(calibration,preset,fixture.config['imports']))
        self.assertEqual((binding['modifier_mask'],binding['trigger_mask']),(0x100,0x400))
        gun=next(i for i,m in enumerate(fixture.config['imports']) if m['id'].startswith('sanada'))
        self.assertAlmostEqual(fixture.config['move_settings'][gun]['speed'],1.15)
        broken=copy.deepcopy(fixture.config);broken['imports'][gun]['flags']^=1
        with self.assertRaises(ValueError): encode_session(broken,fixture.pid,fixture.born)

    def test_portable_launches_preserve_the_owned_worker(self):
        # Reproduce shared extraction using the pinned installer generator's actual option branch.
        # Model launcher cleanup with owned temporary files, then reopen the retained worker.
        # Neither the game nor a real gameplay supervisor is started by this lifetime check.
        import subprocess
        result = subprocess.run(['node', str(ROOT/'tests/portable_worker.cjs')],
                                cwd=ROOT, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)

    def test_desktop_edit_validate_save_and_bind_roundtrip(self):
        # Run the real renderer against a UTF-8 worker with temporary settings only.
        # Simulate physical binding and reject lifecycle calls so this cannot touch Nioh.
        # Exercise inheritance, Unicode, overlap rejection, controller remapping and stale replies together.
        import os
        import subprocess
        import sys
        for command in (['node', '--check', str(ROOT/'tests/desktop_ui.cjs')],
                        ['node', str(ROOT/'desktop/build.mjs')]):
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        with tempfile.TemporaryDirectory(prefix='mwm-ui-') as folder:
            result = subprocess.run([str(ROOT/'node_modules/electron/dist/electron.exe'),
                                     str(ROOT/'tests/desktop_ui.cjs'), folder, sys.executable],
                                    cwd=ROOT, capture_output=True, text=True, timeout=95,
                                    creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            report = Path(folder)/'ui-result.json'
            details = report.read_text(encoding='utf8') if report.exists() else result.stdout+result.stderr
            self.assertEqual(result.returncode, 0, details)
            outcome = json.loads(details)
            self.assertTrue(outcome['explicitNativeSpeed'] and outcome['staleCaptureRejected'] and outcome['frostPreserved']
                            and outcome['customRoutes'] and outcome['customCapture'])

    def test_full_dataset_and_design_references(self):
        # Verify the evidence shipped in this private repository, not a Downloads dependency.
        # Match each requested route to exact dataset phases before presenting its label in the app.
        # This checks provenance and configuration intent without treating candidate names as gameplay proof.
        import importlib.util
        spec = importlib.util.spec_from_file_location('mwm_dataset_validation', ROOT/'dataset/validate.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        moves = module.load_dataset(ROOT/'dataset')
        self.assertTrue(moves)
        self.assertEqual(module.verify_evidence(moves, ROOT/'dataset/evidence'),
                         len({ref['archive_sha256'] for move in moves.values() for ref in move['evidence']}))
        inventory = json.loads((ROOT/'dataset/intake.json').read_text(encoding='utf8'))
        self.assertEqual(module.verify_intake(ROOT/'dataset', moves, ROOT/'dataset/evidence'), len(inventory['sessions']))
        design = json.loads((ROOT/'configurations/sword-rebuild-1.json').read_text(encoding='utf8'))
        for route in design['routes']:
            steps = {step['id']: step['source'] for step in moves[route['dataset_id']]['steps']}
            self.assertEqual(route['source_actions'], [steps[key] for key in route['step_ids']])

    def test_starter_load_remaps_controller_without_applying(self):
        # A built-in preset is still a draft and must translate the saved PlayStation button mapping.
        # Replace settings writers with failing mocks to catch accidental Apply during starter loading.
        # Use the actual MWM worker command; neither the controller nor the game is opened.
        import importlib.util
        import sys
        from unittest.mock import patch
        sys.path.insert(0, str(ROOT/'app'))
        spec = importlib.util.spec_from_file_location('mwm_desktop_review', ROOT/'app/web_worker.py')
        worker = importlib.util.module_from_spec(spec); spec.loader.exec_module(worker)
        calibration = dict(schema=1, device=dict(backend='xinput',slot=0), lb_mask=0x100,
                           lt=dict(axis='lt',neutral=0,full=255),controller_slot=0)
        with patch.object(worker, 'atomic_json', side_effect=AssertionError('Starter must not apply')):
            preset = worker.Desktop().dispatch('starter', dict(calibration=calibration))
        from game_controller import binding_buttons
        buttons = binding_buttons(calibration['device'])
        self.assertEqual(preset['modifier_mask'], 0x100)
        self.assertIn(preset['trigger_mask'], buttons.values())
        self.assertEqual(preset['low_heavy'], 'jin_hayabusa.action_0c6e')

    def test_sword_rebuild_subset_compiles_with_pulse_and_native_speed(self):
        # Compile the new product preset through real dependency selection and the native encoder.
        # Check Pulse inheritance on every selected Jin phase, including dodge and landing continuations.
        # New boss trials stay absent; standing and dodging Mid heavies reuse one Jin graph.
        import json
        from project_paths import DATA
        preset = config.validate_preset(json.loads((DATA/'presets/sword-rebuild-1-supported.json').read_text(encoding='utf8')))
        fixture = sessions.RuntimeSessionTests(); fixture.setUp(); fixture.configured_fixture(preset)
        encoded = encode_session(fixture.config, fixture.pid, fixture.born)
        self.assertIsNone(preset['tap_move'])
        self.assertIsNone(preset['frost_moon']['mid'])
        self.assertEqual(len(preset['skill_bindings']), 3)
        self.assertEqual(preset['low_heavy'], 'jin_hayabusa.action_0c6e')
        self.assertEqual(preset['skill_bindings'][0]['move'], 'jin_hayabusa.action_0c6f')
        self.assertEqual(preset['skill_bindings'][1]['move'], 'jin_hayabusa.action_0bbf')
        self.assertEqual(preset['skill_bindings'][2], dict(source='dodge_attack', stance='mid', move='jin_hayabusa.action_0bbf'))
        standing, dodging = fixture.config['skill_bindings'][1:3]
        self.assertEqual(standing['variant'], dodging['variant'])
        self.assertEqual((dodging['key'], dodging['stances']), (0xBC8, 2))
        self.assertEqual(preset['frost_moon'], dict(low='jin_hayabusa.action_0c71',mid=None,high='jin_hayabusa.action_0c75'))
        jin = [move for move in fixture.config['imports'] if move['id'].startswith('jin_hayabusa.')]
        self.assertEqual(len(jin), 15)  # Three heavy, five quick, four Swallow, three downward-slash phases.
        for index, move in enumerate(fixture.config['imports']):
            if move in jin:
                self.assertEqual(MOVE_SETTINGS.unpack_from(encoded,11640+index*MOVE_SETTINGS.size), (1.,40,30,36,0))

    def test_research_dataset_rejects_misclassification_truncated_ids_and_reversed_strings(self):
        # The fresh collection uses stable weapon/boss paths instead of the legacy runtime catalogue.
        # Copy only curated files, then introduce three realistic authoring mistakes independently.
        # This regression needs no external recording archive, game, UI or spreadsheet library.
        import importlib.util
        import shutil
        dataset = ROOT/'dataset'
        spec = importlib.util.spec_from_file_location('research_dataset', dataset/'validate.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        self.assertTrue(module.load_dataset(dataset))
        with tempfile.TemporaryDirectory() as temporary:
            copy = Path(temporary)/'dataset'; shutil.copytree(dataset, copy)
            file = next(path for path in (copy/'weapons').glob('*/*/*.json')
                        if len(json.loads(path.read_text(encoding='utf8'))['steps']) > 1)
            original = file.read_text(encoding='utf8')
            for mistake in ('weapon', 'action_id', 'order'):
                with self.subTest(mistake=mistake):
                    record = json.loads(original)
                    if mistake == 'weapon': record['weapon_id'] = 'misfiled'
                    elif mistake == 'action_id': record['steps'][0]['source']['action_id'] = 'D8C'
                    else: record['steps'].reverse()
                    file.write_text(json.dumps(record), encoding='utf8')
                    with self.assertRaises(ValueError): module.load_dataset(copy)

