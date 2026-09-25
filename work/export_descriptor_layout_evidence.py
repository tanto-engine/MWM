"""Compact evidence from saved data and previously disassembled native code only."""
import json
import struct
from pathlib import Path

root = Path(__file__).parent
capture = json.loads((root / 'okatsu-c64-bank-resolution.json').read_text())
meta = capture['source_metadata']
raw = bytes.fromhex(meta['descriptor_bytes'])
bases = [0x48, 0x58, 0x68, 0x78, 0x88, 0x98, 0xA8, 0xB8]
bank_offsets = [0x20, 0x30, 0x40, 0x50, 0xC0, 0xD0, 0xE0, 0x100]
assignment_ranges = ['7049B0-7049CC', '7049DC-7049F8', '704A08-704A24',
                     '704A30-704A54', '704B6C-704B88', '704B8F-704BA8',
                     '704BAF-704BC8', '704BCF-704BE8']
result = {
    'mode': 'offline_saved_evidence_only',
    'build_sha256': capture['session']['build_sha256'],
    'slot_size': 0xD0,
    'size_basis': {
        'pool_init_rva': '0x734910', 'allocation_size_rva': '0x734BBE',
        'allocation_bytes': 0x215340, 'slot_count': 0x2904,
        'slot_stride_rva': '0x734BDC', 'free_list_step_rvas': '0x734BF8-0x734C23',
        'pool_global_rva': '0x1871888', 'pool_selector_rva': '0x18717D0',
        'selector_assignment_rvas': '0x734C6B-0x734C72',
        'builder_pop_slot_rvas': '0x704457-0x704474',
        'builder_bank_insert_rvas': '0x704479-0x70448B',
        'bank_teardown_return_slot_rvas': '0x705420-0x705474',
        'scope': 'This exact build uses 0xD0 pool slots for descriptors in bank+0x128. This does not prove a shallow copy is self-contained.'
    },
    'header_layout': {'size': 16, 'pointer_qword_offset': 0, 'start_u16_offset': 8,
                      'count_u16_offset': 10, 'trailing_padding_bytes': 4,
                      'initialization_rvas': '0x7044BF-0x704528'},
    'c64_saved_descriptor': meta['address'],
    'c64_headers': [],
    'pointer_fields': {
        'payload_0x20': hex(struct.unpack_from('<Q', raw, 0x20)[0]),
        'source_bank_plus_0x90_at_0x28': hex(struct.unpack_from('<Q', raw, 0x28)[0]),
        'descriptor_link_0x30': hex(struct.unpack_from('<Q', raw, 0x30)[0]),
        'source_bank_0x38': hex(struct.unpack_from('<Q', raw, 0x38)[0]),
        'source_bank_assignment_rva': '0x7044B7',
        'bank_plus_0x90_assignment_rva': '0x704B68'
    },
    'zeroing_count_0x82': {
        'confirmed_effect': 'Suppresses the descriptor+0x78 transition slice in readers using its count.',
        'count_reader_rvas': ['0x73F88E-0x73F8A5', '0x70DF00-0x70DF08', '0x7171A0-0x7171AE'],
        'not_a_global_transition_disable': [
            {'rvas': '0x717369-0x717398', 'route': 'Actor flag bit29 selects actor+0x260 entry and dispatches virtual+0x208 without consulting current descriptor+0x82.'},
            {'rvas': '0x70E630-0x70E69A', 'route': 'Virtual+0x210 can use actor+0x260 under actor flag bit14 and dispatch virtual+0x208.'},
            {'rvas': '0x710A70-0x710A77', 'route': 'Virtual+0x208 implementation extracts signed target from entry+0x14 and calls virtual+0x1A0.'},
            {'rvas': '0x7172B2-0x7172C9', 'route': 'Separate update branch derives a key from another actor current payload, increments it, and dispatches virtual+0x1A0.'}
        ],
        'separate_timing_bank': 'Saved motion key1220 timing record has33 events. They are separate from the descriptor headers; C64 descriptor+0x58 count is0.',
        'unknown': 'Not every actor flag is semantically named. Global prevention of action changes is neither established nor desirable for death/interruption handling.'
    },
    'limits': [
        'Copied pointers and source-bank backreference still depend on the source allocations remaining alive.',
        'No claim that zeroing all slices would be safe or preserve the attack.',
        'No memory writes or live process access performed.'
    ]
}
for base, bank_offset, assignment in zip(bases, bank_offsets, assignment_ranges):
    pointer, start, count = struct.unpack_from('<QHH', raw, base)
    result['c64_headers'].append({'base': hex(base), 'bank_table_offset': hex(bank_offset),
                                 'pointer': hex(pointer), 'start': start, 'count': count,
                                 'count_offset': hex(base + 10), 'assignment_rvas': assignment})
assert result['size_basis']['allocation_bytes'] == result['slot_size'] * result['size_basis']['slot_count']
(root / 'okatsu-descriptor-layout-evidence.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({'slot_size': result['slot_size'], 'counts': [x['count'] for x in result['c64_headers']],
                  'source_bank': result['pointer_fields']['source_bank_0x38']}))
