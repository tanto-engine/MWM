"""Package original code, licenses and compact verification evidence; no game assets."""
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs'
TARGET = OUT / 'okatsu-prototype'


def load(relative):
    return json.loads((ROOT / relative).read_text(encoding='utf-8-sig'))


def main():
    profile = load('outputs/okatsu-prototype/session-profile.json')
    evidence = TARGET / 'evidence'
    evidence.mkdir(exist_ok=True)
    for source, name in [
        ('work/lb-lt-native-take1/input-native-events.jsonl', 'lb-lt-input-action-trace.jsonl'),
        ('work/lb-lt-native-take1/status.json', 'lb-lt-capture-status.json'),
        ('work/okatsu-descriptor-layout-evidence.json', 'descriptor-layout.json')]:
        shutil.copyfile(ROOT / source, evidence / name)
    tests = []
    for folder in sorted([*(ROOT / 'work').glob('player-dispatch-test*'),
                          *(ROOT / 'work').glob('okatsu-preview-test*'), ROOT/'work/okatsu-play1']):
        if not (folder / 'status.json').exists():
            continue
        test = load(str((folder / 'status.json').relative_to(ROOT)))
        tests.append(dict(name=folder.name, **test))
        destination = evidence / folder.name
        destination.mkdir(exist_ok=True)
        for path in folder.iterdir():
            if path.is_file():
                shutil.copyfile(path, destination / path.name)
    finding = dict(
        status='LB+Circle moves, movement, lock-on, stance retention and voice removal confirmed by user; startup/Ki Pulse changes await live verification',
        target=dict(character='Okatsu', user_description='Charged Rush', binding='LB+Circle tap/release',
                    candidate_action_key='0x0C64', visual_match_confirmed=True,
                    motion_key=1220, timing_key=1220),
        charged_target=dict(user_description='Leaping Slash', binding='LB+Circle hold 0.25s',
                            action_key='0x0C66', motion_key=1230, timing_key=1230,
                            native_dispatch_and_loaded_resources_verified=True,
                            user_feedback='Works as intended'),
        build_sha256=profile['session']['build_sha256'],
        controller=dict(backend='winmm', slot=0, lb_mask='0x10', circle_mask='0x4',
                        hold_seconds=.25, saved_calibration_reused=True),
        voice_filter=dict(user_confirmed_removed=True, combat_fx_retained=True,
                          scope='Only imported AV_OKATSU_SKILL_SHORT and AV_OKATSU_ATTACK_STRONG events'),
        startup_change=dict(action_key='0x0C64', multiplier=2, frames=[0, 30],
                            motion_and_timing_clocks_synchronized=True, live_verified=False),
        ki_pulse_change=dict(window_start_frames={'0x0C64': 65, '0x0C66': 90},
                             recoverable_cost_percent=40, fill_frames=25, hold_frames=24,
                             native_cost_preserved=True, native_pulse_rows_appended=3,
                             live_verified=False),
        native_input_observation=dict(chords=3, player_calls=21, dropped=0,
                                      request_0x18_resolves='0x0CE7', request_0x19_resolves='0x0CE8',
                                      scope='Observed temporal association in this sword session'),
        implemented=['Independent DLL loader and original action observer',
                     'Timestamped controller/action tracing with requested and resolved IDs',
                     'Regular/hold gesture scheduling on native action-node update',
                     'Private full action records preserving current player stance',
                     'Loaded boss motion/timing resource binding and recovery restoration',
                     'Continuous play with clean actor/session reacquisition',
                     'Focused imported voice suppression preserving combat FX',
                     'Charged Rush startup acceleration through frame30; awaiting live verification',
                     'Native Ki recovery metadata and player pulse input transitions; awaiting live verification',
                     'Process/build/actor/bank/descriptor validation and expiring gesture intent'],
        boss_resource_findings=dict(animation_absent_from_player=True, timing_absent_from_player=True,
                                    source_timing_event_count=33, all_event_meanings_resolved=False,
                                    resource_resolution_is_deferred_after_action_setter=True,
                                    shallow_descriptor_copy_does_not_isolate_all_transitions=True),
        remaining=['Verify Charged Rush startup acceleration and both native Ki Pulse windows in gameplay',
                   'Verify player damage ownership',
                   'Make boss resources available outside her loaded mission'],
        live_tests=tests,
        dependencies=dict(MinHook='v1.3.4, BSD license included; third-party hook library'),
        scope='Exact researched build only. Process-specific pointers must be reacquired after reload. '
              'No game files or assets are modified. DLLs remain loaded but inactive after Stop until game exit.')
    (TARGET / 'findings.json').write_text(json.dumps(finding, indent=2) + '\n')
    archive = OUT / 'Nioh1-Sword-Native-Prototype.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
        for folder in (TARGET, OUT / 'boss-probe'):
            for path in sorted(folder.rglob('*')):
                if (path.is_file() and '__pycache__' not in path.parts and 'sessions' not in path.parts
                        and path.suffix != '.o' and path.name not in ('play-process.json','play-status.json','stop.flag')
                        and not path.name.startswith('harness_')):
                    bundle.write(path, path.relative_to(OUT))
    print(json.dumps(dict(archive=str(archive), tests=len(tests))))


if __name__ == '__main__':
    main()
