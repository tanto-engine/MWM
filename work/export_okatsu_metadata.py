import csv
import json
from pathlib import Path

out = Path('outputs/Okatsu-Capture-30s')
events = [json.loads(line) for line in (out / 'events.jsonl').read_text().splitlines()]
records, targets = [], []
for event in events:
    if event['kind'] != 'metadata':
        continue
    payload = event.get('payload_prefix', {})
    sl = event['transition_slice']
    common = dict(t=event['t'], object=event['object'], provisional_role=event['role'],
                  descriptor=event['address'], word0_hex=event['word0_hex'],
                  matches_preceding_state=event['matches_preceding_state'])
    records.append(dict(**common, payload=event['payload'],
                        payload_key_i16=payload.get('key_0x0c_i16', ''),
                        flags_u64=payload.get('flags_0x18_u64', ''),
                        flag_bit34=payload.get('flag_bit34', ''), flag_bit35=payload.get('flag_bit35', ''),
                        related_key_i16=payload.get('related_key_0x30_i16', ''),
                        transition_table=sl['table'], slice_start=sl['start'], slice_count=sl['count'],
                        entries_requested=event['entries_requested'], entries_omitted=event['entries_omitted']))
    for entry in event['transition_entries']:
        targets.append(dict(**common, table_index=entry['table_index'], entry_address=entry['address'],
                            lookup_target_i16=entry.get('target_key_0x14_i16', ''),
                            byte_0x0a=entry.get('byte_0x0a', ''), condition_i32=entry.get('condition_0x2c_i32', ''),
                            read_error=entry.get('error', ''),
                            interpretation='Potential transition lookup key; not proof this transition occurred'))
for name, rows in [('record_metadata.csv', records), ('transition_metadata.csv', targets)]:
    with (out / name).open('x', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
print(json.dumps(dict(metadata_rows=len(records), transition_rows=len(targets))))
