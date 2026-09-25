"""Package original prototype sources and a compact, evidence-based finding."""
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
read = lambda path: json.loads((ROOT / path).read_text(encoding='utf-8-sig'))
ranking = read('work/okatsu-first-move-ranking.json')
data = read('work/okatsu-c64-bank-resolution.json')
candidate = next(r for r in ranking['record_ranking'] if r['word0'] == '0x0C64')
comparisons = data['direct_transition_comparisons']
finding = {
    'status': 'Research prototype; gameplay execution is not implemented or enabled',
    'target_description_from_user': 'Okatsu rushing or leaping sword attack',
    'candidate_key_hex': '0x00000C64',
    'visual_identity_confirmed': False,
    'selection': {
        'observed_entries_in_30_second_take': candidate['observed_entries'],
        'complete_dwell_seconds': candidate['complete_dwell_seconds'],
        'basis': ranking['candidate_for_visual_identification']['basis'],
        'dwell_is_frame_data': False,
    },
    'build_sha256': data['session']['build_sha256'],
    'native_lookup': {
        'rva': data['native_lookup_rva'],
        'actor_bank_pointer_offsets': ['0x70', '0x78', '0x80'],
        'bank_descriptor_pointer_array_offset': '0x128',
        'bank_descriptor_count_u32_offset': '0x130',
        'descriptor_key_u32_offset': '0x00',
        'descriptor_enable_u8_offset': '0x40',
        'priority': 'First enabled exact DWORD match, bank 0 then 1 then 2',
        'transition_target': 'Signed 16-bit at +0x14; -1 is a rejected sentinel',
        'action_setter_rva': '0x7119C0',
        'action_setter_input_range': 'Rejects unsigned EDX greater than 0xFFFE',
        'action_setter_context': 'R8 optionally supplies a lookup context; otherwise actor+0x70 is used. Downstream animation compatibility is unproven.',
    },
    'session_only_example': {
        'source_actor_candidate': data['source_actor']['object'],
        'destination_actor_candidate': data['destination_actor']['object'],
        'source_resolution': data['source_resolution'],
        'destination_resolution': data['destination_resolution'],
        'addresses_are_reusable_after_reload': False,
    },
    'transition_comparison': {
        'entries_in_source_descriptor': data['source_metadata']['transition_slice'],
        'unique_non_sentinel_keys_in_raw_entries': len(comparisons),
        'same_descriptor_in_player': sum(c['same_descriptor'] for c in comparisons),
        'different_descriptor_in_player': sum(c['destination'] is not None and not c['same_descriptor'] for c in comparisons),
        'missing_in_player': [f"0x{c['transition_key_i16'] & 0xffff:04X}" for c in comparisons if c['destination'] is None],
        'interpretation': 'Raw references, not proof all branches execute or need importing. Generic exits may intentionally use player records; boss follow-ups require individual review.',
    },
    'implemented': [
        'External read-only native bank resolver and cross-actor comparison',
        'Pure LB+LT chord gate with release-to-rearm and LT hysteresis',
    ],
    'pending': [
        'Calibrate this physical controller: LB alone, LT alone, then chord',
        'Route the chord without also executing conflicting normal bindings',
        'Visually correlate C64 with the requested move',
        'Trace selected bank and payload to animation resources and event execution',
        'Choose isolated action routing with deliberate player recovery',
        'Validate skeleton, root motion, sword hit events and player damage ownership',
        'Implement and test dispatch on the game update thread',
    ],
    'first_playable_scope': 'One move while Okatsu resources are loaded; loading in other missions requires resource lifetime handling',
    'asset_plan': 'Attempt reuse first. Convert or retarget only after demonstrating an incompatible binding; existing data does not yet prove that new assets are needed.',
    'limitations': ['Actor roles are evidence-supported candidates', 'Memory snapshots are non-atomic', 'Action references are not globally unique animation IDs'],
    'game_modified': False,
}
target = ROOT / 'outputs/okatsu-prototype'
(target / 'findings.json').write_text(json.dumps(finding, indent=2) + '\n', encoding='utf-8')
for folder, archive in [('boss-probe', 'Nioh1-Boss-Probe.zip'), ('okatsu-prototype', 'Okatsu-Prototype-Research.zip')]:
    with zipfile.ZipFile(ROOT / 'outputs' / archive, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted((ROOT / 'outputs' / folder).rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts:
                bundle.write(path, path.relative_to(ROOT / 'outputs'))
print(json.dumps({'key': finding['candidate_key_hex'], 'entries': candidate['observed_entries'], 'references': finding['transition_comparison'], 'game_modified': False}, indent=2))
