# The workbook owns move metadata in ordinary cells. The simple visible sheets
# and the inspectable supporting tables travel together as one maintained file.
import io
import math
import os
from pathlib import Path
import posixpath
import re
import struct
import tempfile
import textwrap
import xml.etree.ElementTree as ET
import zipfile

if __package__:
    from .catalogue import iter_moves, load_catalogue, validate_catalogue
else:
    from catalogue import iter_moves, load_catalogue, validate_catalogue

FILENAME = 'Nioh1-Sword-Move-Observations.xlsx'
MAIN = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
NS = {'m': MAIN}
ET.register_namespace('x', MAIN)
ET.register_namespace('r', REL)
MOVE_HEADERS = ['Boss', 'Move / string', 'Ordered source IDs (hex)', 'Designation', 'Binding', 'Evidence', 'Status']
OBSERVATION_HEADERS = ['Actor', 'Observation', 'Category', 'Source ID (hex)', 'Animation / timing', 'Seen', 'Verification', 'Evidence', 'Catalogue ID']
WEAPON_SECTIONS = (('sword', 'Sword'), (None, 'Unclassified'))


def source_ids(source):
    # Render source identity without inventing missing metadata.
    # Distinguish full action keys from unresolved low-word observations.
    # Animation and timing remain separate decimal references.
    action = source.get('action_id')
    sampled = source.get('observed_word0_u16')
    if action is not None:
        identity = f'{action:04X}h'
    elif sampled is not None:
        identity = f'word0 {sampled:04X}h (unresolved)'
    else:
        identity = 'Unknown'
    motion, timing = source.get('motion_id'), source.get('timing_id')
    animation = f'{motion if motion is not None else "?"} / {timing if timing is not None else "?"}'
    return identity, animation


def workbook_sections(catalogue):
    # Build the simple move view grouped by populated weapons.
    # Keep named moves and project only boss, name, ID and designation.
    # Unclassified actions stay available in the observation view.
    bosses = {boss['id']: boss['name'] for boss in catalogue['bosses']}
    sections = {key: {'key': key, 'name': name, 'rows': [], 'ids': []} for key, name in WEAPON_SECTIONS}
    for move in catalogue['moves']:
        if move['name_status'] == 'unclassified':
            continue
        if move['weapon'] not in sections:
            raise ValueError(f"Unknown weapon section: {move['weapon']}")
        designation = move.get('designation', 'unclassified')
        if designation not in ('normal', 'quick', 'heavy', 'skill', 'grab', 'unclassified'):
            raise ValueError(f'Unknown move designation: {designation}')
        binding = move.get('default_binding')
        control = 'Unassigned' if not binding else ' + '.join(binding['chord']) + ': ' + binding['gesture'].replace('_', ' ')
        if binding and binding.get('stance'):
            control = binding['stance'].capitalize() + ' ' + control
        evidence = next((item['path'].replace('\\', '/') for item in move['evidence'] if item.get('path')), 'Classification pending')
        status = move['verification'].get('player_use', move['implementation']['status']).replace('_', ' ')
        sections[move['weapon']]['rows'].append([bosses[move['boss_id']], move['name'], move_source_ids(move), designation.capitalize(), control, evidence, status])
        sections[move['weapon']]['ids'].append(move['id'])
    return [section for section in sections.values() if section['rows']]


def move_source_ids(move):
    # Show the entry action and its ordered constituent identities together.
    # Derive the sequence from retained records rather than duplicate metadata.
    # Source order describes the string while evidence retains classification limits.
    return ' > '.join(source_ids(item['source'])[0] for item in iter_moves({'moves': [move]}))


def workbook_rows(catalogue):
    # Project both views from the same authoritative catalogue.
    # Append unresolved move records to the retained observation ledger.
    # Simplifying the main sheet must never discard captured evidence.
    moves = [row for section in workbook_sections(catalogue) for row in section['rows']]
    bosses = {boss['id']: boss['name'] for boss in catalogue['bosses']}
    # Interrupted captures may retain only a boss and evidence. Show their
    # missing identity/count explicitly instead of losing the observation.
    observations = []
    records = catalogue['observations'] + [move for move in catalogue['moves'] if move['name_status'] == 'unclassified']
    for item in records:
        action, animation = source_ids(item['source'] if 'source' in item else {})
        actor = 'Unknown actor'
        if item['boss_id'] is not None:
            actor = bosses[item['boss_id']]
        elif 'actor' in item:
            actor = item['actor']
        elif 'actor_label' in item:
            actor = item['actor_label']
        name = item['name'] if 'name' in item else 'Unclassified'
        category = item['category'] if 'category' in item else item.get('role', 'unclassified')
        capture = item['capture'] if 'capture' in item else {}
        seen = capture['state_events'] if 'state_events' in capture else item.get('observations')
        reference = 'No source path recorded'
        for evidence in item['evidence']:
            if 'path' in evidence:
                reference = evidence['path']
                if 'line' in evidence:
                    reference += f":{evidence['line']}"
                break
        status = item['implementation']['status'] if 'implementation' in item else item['status']
        observations.append([actor, name, category.replace('_', ' '), action, animation, seen, status.replace('_', ' '), reference, item['id']])
    return moves, observations


def workbook_links(parts, source):
    # Resolve worksheet and table relationships inside the archive.
    # Join each relationship target against its owning XML part.
    # Writers address the actual workbook parts instead of guessing filenames.
    folder, name = posixpath.split(source)
    relationships = ET.fromstring(parts[f'{folder}/_rels/{name}.rels'])
    return {link.attrib['Id']: posixpath.normpath(posixpath.join(folder, link.attrib['Target'])).lstrip('/') for link in relationships}


def row_styles(data, number, columns):
    # Reuse the workbook's existing row formatting templates.
    # Read style IDs from the selected XML row, including default style zero.
    # Data refreshes preserve the artifact-authored layout.
    row = data.find(f'm:row[@r="{number}"]', NS)
    if row is None:
        raise ValueError(f'Workbook style template row {number} is absent')
    styles = ['0'] * columns  # OOXML omits the style attribute for its default style.
    for cell in row:
        column = 0
        for letter in re.match('[A-Z]+', cell.attrib['r'])[0]:
            column = column * 26 + ord(letter) - 64
        column -= 1
        if column < columns:
            styles[column] = cell.attrib.get('s', '0')
    return styles


def column_widths(sheet, count):
    # Expand Excel column spans into one width per displayed column.
    # Read the sheet's column definitions and fill each covered index.
    # Wrapped-row sizing uses the authored widths.
    widths = [None] * count
    for column in sheet.find('m:cols', NS):
        for index in range(int(column.attrib['min']) - 1, min(count, int(column.attrib['max']))):
            widths[index] = float(column.attrib['width'])
    if None in widths:
        raise ValueError('Workbook column widths are absent')
    return widths


def append_row(data, number, values, styles, widths, height=None):
    # Serialize one literal data row with explicit cell types.
    # Write numbers as values and text as inline strings with shared styles.
    # Names starting with an equals sign never become formulas.
    if height is None:
        height = max(32, 15 * max(len(textwrap.wrap(str(value), max(1, int(widths[column]) - 3))) for column, value in enumerate(values)) + 8)
    row = ET.SubElement(data, f'{{{MAIN}}}row', {'r': str(number), 'ht': str(height), 'customHeight': '1'})
    # Literal strings cannot turn a newly named move into an Excel formula.
    for column, value in enumerate(values):
        cell = ET.SubElement(row, f'{{{MAIN}}}c', {'r': f'{excel_column(column)}{number}', 's': styles[column]})
        if value is None:
            continue
        if isinstance(value, (int, float)):
            if not math.isfinite(value):
                raise ValueError('Non-finite workbook number')
            ET.SubElement(cell, f'{{{MAIN}}}v').text = str(value)
        else:
            if len(value) > 32767 or re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', value):
                raise ValueError('Catalogue text exceeds Excel limits')
            cell.set('t', 'inlineStr')
            ET.SubElement(ET.SubElement(cell, f'{{{MAIN}}}is'), f'{{{MAIN}}}t', {'{http://www.w3.org/XML/1998/namespace}space': 'preserve'}).text = value


def replace_move_sections(parts, sheet_path, sections):
    # Refresh the four-column view without creating duplicate tables.
    # Rebuild populated bands, headers and body rows from style templates.
    # Weapon sections can grow or disappear without stale merge ranges.
    sheet = ET.fromstring(parts[sheet_path])
    if sheet.find('m:tableParts', NS) is not None:
        raise ValueError('Moves must use plain weapon sections without tables')
    data = sheet.find('m:sheetData', NS)
    columns_count = len(MOVE_HEADERS)
    banner_style, header_style, body_style = [row_styles(data, number, columns_count) for number in (1, 2, 3)]
    widths = column_widths(sheet, columns_count)
    banner_height = data.find('m:row[@r="1"]', NS).attrib['ht']
    header_height = data.find('m:row[@r="2"]', NS).attrib['ht']
    data.clear()
    merges = sheet.find('m:mergeCells', NS)
    if merges is None:
        raise ValueError('Moves is missing its section banner template')
    merges.clear()
    number = 1
    # Retain the three style rows in an empty catalogue so later discoveries can
    # populate it without rebuilding the workbook or requiring a new template.
    for section in sections or [{'name': '', 'rows': [[None] * columns_count]}]:
        append_row(data, number, [section['name']] + [None] * (columns_count-1), banner_style, widths, banner_height)
        ET.SubElement(merges, f'{{{MAIN}}}mergeCell', {'ref': f'A{number}:G{number}'})
        append_row(data, number + 1, MOVE_HEADERS, header_style, widths, header_height)
        number += 2
        for index, values in enumerate(section['rows']):
            append_row(data, number, values, body_style, widths)
            if 'ids' in section:
                row = data[-1]
                cell = ET.SubElement(row, f'{{{MAIN}}}c', {'r': f'H{number}', 't': 'inlineStr'})
                ET.SubElement(ET.SubElement(cell, f'{{{MAIN}}}is'), f'{{{MAIN}}}t').text = section['ids'][index]
            number += 1
        number += 1
    merges.set('count', str(len(merges)))
    columns = sheet.find('m:cols', NS)
    hidden = next((item for item in columns if item.attrib['min'] == '8'), None)
    if hidden is None:
        hidden = ET.SubElement(columns, f'{{{MAIN}}}col', {'min': '8', 'max': '8', 'width': '36', 'customWidth': '1'})
    hidden.set('hidden', '1')
    dimension = sheet.find('m:dimension', NS)
    if dimension is not None:
        dimension.set('ref', f'A1:H{number - 2}')
    parts[sheet_path] = ET.tostring(sheet, encoding='utf-8', xml_declaration=True)


def replace_table(parts, sheet_path, headers, rows):
    # Refresh observations while preserving its existing Excel table.
    # Replace body cells and update the table's range and filter bounds.
    # Historical evidence remains filterable after the catalogue grows.
    sheet = ET.fromstring(parts[sheet_path])
    data = sheet.find('m:sheetData', NS)
    styles = row_styles(data, 2, len(headers))
    widths = column_widths(sheet, len(headers))
    for row in list(data)[1:]:
        data.remove(row)
    for number, values in enumerate(rows or [[None] * len(headers)], 2):
        append_row(data, number, values, styles, widths)
    reference = f'A1:{chr(64 + len(headers))}{max(2, len(rows) + 1)}'
    dimension = sheet.find('m:dimension', NS)
    if dimension is not None:
        dimension.set('ref', reference)
    links = workbook_links(parts, sheet_path)
    table_id = sheet.find('m:tableParts/m:tablePart', NS).attrib[f'{{{REL}}}id']
    table_path = links[table_id]
    table = ET.fromstring(parts[table_path])
    if [column.attrib['name'] for column in table.find('m:tableColumns', NS)] != headers:
        raise ValueError(f'Unexpected columns in {sheet_path}')
    table.set('ref', reference)
    table.find('m:autoFilter', NS).set('ref', reference)
    parts[sheet_path] = ET.tostring(sheet, encoding='utf-8', xml_declaration=True)
    parts[table_path] = ET.tostring(table, encoding='utf-8', xml_declaration=True)



# Explicit tables keep editable source facts in cells and related evidence in rows.
# The schema is intentionally closed: a new recorded field must receive a column.
# No workbook cell contains a serialized Python object or a JSON document.
SCHEMAS = {
    'Catalogue': {'schema_version': 'i', 'game': 's', 'supported_build_sha256': 's', 'identity_policy': 's', 'bosses': '*Bosses', 'moves': '*Moves', 'observations': '*Observations', 'encounters': '*Encounters'},
    'Bosses': {'id': 's', 'name': 's', 'weapon': 's', 'weapons': 'S', 'capture_signature': '*Signatures'},
    'Signatures': {'action_id': 'i', 'motion_id': 'i'},
    'Moves': {'id': 's', 'boss_id': 's', 'name': 's', 'name_status': 's', 'category': 's', 'weapon': 's', 'designation': 's', 'designation_basis': 's', 'resource_profile_id': 's', 'source': '@Source', 'default_binding': '@Binding', 'implementation': '@Implementation', 'verification': '@Verification', 'adaptation': '@Adaptation', 'capture': '@Capture', 'combo': '@Combo', 'evidence': '*Evidence', 'limitations': 'S', 'source_conflicts': '*Conflicts', 'steps': '*Moves'},
    'Observations': {'id': 's', 'boss_id': 's', 'actor': 's', 'actor_label': 's', 'name': 's', 'category': 's', 'role': 's', 'status': 's', 'source': '@Source', 'capture': '@Capture', 'observations': 'i', 'evidence': '*Evidence', 'limitations': 'S', 'candidate_move_ids': 'S'},
    'Source': {'actor': 's', 'action_bank': 's', 'action_id': 'i', 'action_hex': 's', 'observed_word0_u16': 'i', 'motion_id': 'i', 'timing_id': 'i', 'timing_override': 'i', 'transition_row_count': 'i', 'flags': 'i', 'ki_cost': 'i', 'recovery_frame': 'i', 'transition_targets': 'I', 'cancel_frame': 'i', 'ki_pulse_percent': 'i', 'ki_pulse_start': 'i', 'ki_pulse_fill': 'i', 'ki_pulse_hold': 'i', 'transition_links': '*Transition links', 'combat_rows': '*Combat rows', 'transition_rows_total': 'i', 'transition_rows_omitted': 'i', 'combat_rows_total': 'i', 'combat_rows_omitted': 'i'},
    'Binding': {'chord': 'S', 'gesture': 's', 'hold_seconds': 'f', 'stance': 's', 'weapon': 's', 'status': 's', 'chain_position': 'i', 'replaces_action_id': 'i', 'window_seconds': 'f'},
    'Implementation': {'status': 's', 'selectable': 'b', 'engine_profile': 's', 'current_build': 's', 'evidence': 's', 'configuration': 's'},
    'Verification': dict.fromkeys(('player_use', 'movement', 'lock_on', 'stance_retention', 'boss_voice_removed', 'combat_effects', 'william_voice', 'damage_ownership', 'damage', 'ki_damage', 'ki_consumption', 'ki_pulse', 'cold_launch_resources', 'lifecycle_recovery', 'startup', 'classification', 'camera', 'native_playback', 'native_boss_pair', 'player_contact', 'victim_routing', 'launcher_animation', 'player_animation', 'visual_name', 'animation', 'sprint_attacks', 'native_boss_playback', 'followups', 'interruptions', 'menus', 'cutscenes', 'death_retry', 'mission_reload', 'equipment_changes'), 's'),
    'Adaptation': {'base_ki_cost': 'i', 'ki_pulse': '@Ki Pulse', 'startup': '@Startup', 'audio': '@Audio', 'stance': 's', 'targeting': 's', 'followups': 's', 'player_action_id': 'i', 'transition_policy': 's', 'source_victim_action': 'i', 'source_victim_motion': 'i', 'status': 's', 'source_clip_frames': 'i', 'clip_frames': 'i', 'native_fields': '*Native fields', 'requests': '*Requests'},
    'Ki Pulse': {'start_frame': 'i', 'recoverable_fraction': 'f', 'fill_frames': 'i', 'hold_frames': 'i', 'status': 's', 'original_start_frame': 'i'},
    'Startup': {'multiplier': 'i', 'start_frame': 'i', 'end_frame': 'i', 'skip_frames': 'b', 'synchronized_motion_timing': 'b', 'status': 's'},
    'Audio': {'suppressed_imported_events': 'S', 'william_voice_event': 's', 'scope': 's'},
    'Capture': {'source': 's', 'entries': 'i', 'state_events': 'i', 'first_seconds': 'f', 'last_seconds': 'f', 'evidence': '*Evidence'},
    'Combo': {'observed_successors': '*Links', 'strings': '*Strings', 'confirmed_followups': 'S', 'status': 's', 'configured_window': 'I', 'native_relationship': 's'},
    'Links': {'actor_label': 's', 'from': 's', 'to': 's', 'count': 'i', 'evidence': '*Evidence', 'relationship': 's'},
    'Strings': {'path': 's', 'section': 's', 'status': 's'},
    'Evidence': {'path': 's', 'line': 'i', 't': 'f', 'kind': 's', 'detail': 's', 'section': 's', 'date': 's', 'sheet': 's', 'row': 'i', 'segment': 's'},
    'Encounters': {'id': 's', 'sha256': 's', 'boss_id': 's', 'path': 's', 'complete': 'b', 'issues': 'S', 'source_sha256': 's'},
    'Conflicts': {'fields': '@Conflicting fields', 'evidence': '*Evidence', 'status': 's'},
    'Conflicting fields': {'motion_id': '@Conflict values', 'timing_id': '@Conflict values', 'timing_override': '@Conflict values'},
    'Conflict values': {'catalogue': 'i', 'observed': 'i'},
    'Transition links': {'row_index': 'i', 'target_action_id': 'i', 'kind': 's', 'conditions': 'I', 'mode': 'i', 'input_id': 'i', 'selectors': 'I', 'target_options': 'I', 'flags': 'i', 'window_frames': 'I', 'raw_hex': 's'},
    'Combat rows': {'row_index': 'i', 'flags': 's', 'ground_horizontal': 'i', 'ground_vertical': 'i', 'air_horizontal': 'i', 'air_vertical': 'i', 'raw_hex': 's'},
    'Native fields': {'name': 's', 'field': 's', 'encoding': 's', 'original': 'i', 'modified': 'i', 'applied': 'b', 'scope': 's', 'status': 's'},
    'Requests': {'feature': 's', 'original': 's', 'requested': 's', 'mechanism': 's', 'scope': 's', 'status': 's'},
}
DATA_SHEET = 'Move data'
NULL = '[not set]'
EMPTY = '[empty]'


def catalogue_tables(catalogue):
    # Split the catalogue into the fixed human-readable tables above.
    # Related rows use parent IDs and positions so repeated evidence keeps its order.
    # Unknown columns fail here instead of disappearing during workbook publication.
    tables = {name: [] for name in SCHEMAS}
    def append_record(table, record, parent, position):
        # Write one explicitly defined record and its related rows.
        # Reject unsupported fields and retain null versus absent values in cells.
        # This keeps recorder discoveries lossless through a spreadsheet round trip.
        schema = SCHEMAS[table]
        unknown = record.keys() - schema.keys()
        if unknown:
            raise ValueError(f'{table}: no workbook columns for {sorted(unknown)}')
        row = [parent, position]
        identity = record.get('id', f'{parent}[{position}]')
        for field, kind in schema.items():
            if field not in record:
                row.append(None)
                continue
            value = record[field]
            if value is None:
                row.append(NULL)
            elif kind.startswith(('@', '*')):
                records = [value] if kind[0] == '@' else value
                row.append(len(records))
                for index, child in enumerate(records):
                    append_record(kind[1:], child, f'{identity}/{field}', index)
            elif kind in ('S', 'I'):
                if any('\n' in str(item) for item in value):
                    raise ValueError(f'{identity}/{field}: a list item contains a line break')
                row.append('\n'.join(map(str, value)) if value else EMPTY)
            elif kind == 'b':
                if type(value) is not bool:
                    raise ValueError(f'{identity}/{field}: expected boolean')
                row.append('Yes' if value else 'No')
            else:
                if isinstance(value, str) and value in (NULL, EMPTY):
                    raise ValueError(f'{identity}/{field}: reserved workbook marker')
                row.append(EMPTY if value == '' else value)
        tables[table].append(row)
    append_record('Catalogue', catalogue, 'catalogue', 0)
    return tables


def catalogue_from_tables(tables):
    # Read the fixed tables back into the existing catalogue API shape.
    # Follow explicit parent references and reject missing, duplicate or orphan rows.
    # A spreadsheet edit cannot silently detach source facts or evidence.
    indexed = {}
    for table, rows in tables.items():
        for row in rows:
            key = (table, row[0], row[1])
            if key in indexed:
                raise ValueError(f'Duplicate workbook record: {key}')
            indexed[key] = row[2:]
    def read_record(table, parent, position):
        # Reconstruct one record using only columns in its declared table.
        # Resolve its child counts against their parent IDs before consuming them.
        # Leftover rows expose broken relationships rather than being ignored.
        row = indexed.pop((table, parent, position))
        schema = SCHEMAS[table]
        values = dict(zip(schema, row))
        identity = values.get('id') or f'{parent}[{position}]'
        record = {}
        for field, kind in schema.items():
            value = values[field]
            if value is None:
                continue
            if value == NULL:
                record[field] = None
            elif kind.startswith(('@', '*')):
                count = int(value)
                if count < 0 or count != value or kind[0] == '@' and count != 1:
                    raise ValueError(f'{identity}/{field}: invalid related-row count')
                children = [read_record(kind[1:], f'{identity}/{field}', index) for index in range(count)]
                record[field] = children[0] if kind[0] == '@' else children
            elif kind in ('S', 'I'):
                record[field] = [] if value == EMPTY else str(value).split('\n')
                if kind == 'I':
                    record[field] = [int(item) for item in record[field]]
            elif kind == 'b':
                if value not in ('Yes', 'No'):
                    raise ValueError(f'{identity}/{field}: expected Yes or No')
                record[field] = value == 'Yes'
            elif kind == 'i':
                record[field] = int(value)
                if record[field] != value:
                    raise ValueError(f'{identity}/{field}: expected whole number')
            elif kind == 'f':
                record[field] = float(value)
            else:
                record[field] = '' if value == EMPTY else str(value)
        return record
    catalogue = read_record('Catalogue', 'catalogue', 0)
    if indexed:
        raise ValueError(f'Orphan workbook record: {next(iter(indexed))}')
    return catalogue


def sheet_cells(parts, path):
    # Read literal worksheet values through standard OOXML cell types.
    # Resolve shared and inline strings while rejecting formulas in metadata cells.
    # Workbook edits remain data rather than executable spreadsheet expressions.
    shared = []
    if 'xl/sharedStrings.xml' in parts:
        shared = [''.join(item.itertext()) for item in ET.fromstring(parts['xl/sharedStrings.xml'])]
    result = {}
    for cell in ET.fromstring(parts[path]).findall('m:sheetData/m:row/m:c', NS):
        if cell.find('m:f', NS) is not None:
            raise ValueError(f'Catalogue cells must contain literal values: {path}!{cell.attrib["r"]}')
        value = cell.find('m:v', NS)
        kind = cell.attrib.get('t')
        if kind == 'inlineStr':
            value = ''.join(cell.find('m:is', NS).itertext())
        elif value is not None and value.text is not None:
            value = shared[int(value.text)] if kind == 's' else value.text if kind == 'str' else float(value.text)
        else:
            value = None
        result[cell.attrib['r']] = value
    return result


def excel_column(index):
    # Convert a zero-based column index into an Excel reference.
    # Repeated division supports technical tables wider than twenty-six columns.
    # Both their writer and reader use the same unambiguous cell addresses.
    name = ''
    while index >= 0:
        index, digit = divmod(index, 26)
        name = chr(65 + digit) + name
        index -= 1
    return name


def data_rows(tables):
    # Lay out each fixed table as a titled block of ordinary cells.
    # Keep fields in schema order and separate blocks with a blank row.
    # Unhiding Move data exposes every technical fact without another file format.
    rows = [['Catalogue metadata: edit facts below; blank means absent, [not set] means unknown, [empty] means an empty list/text.']]
    for table, schema in SCHEMAS.items():
        rows.extend([[table], ['Parent', 'Position', *schema], *tables[table], []])
    return rows


def read_workbook_catalogue(path):
    # Load catalogue metadata from the workbook's ordinary supporting cells.
    # Overlay the simple visible move labels using stable IDs rather than row numbers.
    # The workbook is the sole metadata authority for recorder and trainer readers.
    with zipfile.ZipFile(path) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    sheets = ET.fromstring(parts['xl/workbook.xml']).find('m:sheets', NS)
    links = workbook_links(parts, 'xl/workbook.xml')
    paths = {sheet.attrib['name']: links[sheet.attrib[f'{{{REL}}}id']] for sheet in sheets}
    cells = sheet_cells(parts, paths[DATA_SHEET])
    tables = {name: [] for name in SCHEMAS}
    table = None
    for number in range(2, max(int(re.search(r'\d+$', cell)[0]) for cell in cells) + 1):
        first = cells.get(f'A{number}')
        if first in SCHEMAS and cells.get(f'B{number}') is None:
            table = first
            headers = [cells.get(f'{excel_column(column)}{number+1}') for column in range(len(SCHEMAS[table]) + 2)]
            # Existing workbooks may omit only newly appended optional columns.
            # Renamed, reordered or missing interior fields remain malformed.
            while headers and headers[-1] is None:
                headers.pop()
            if headers != ['Parent', 'Position', *SCHEMAS[table]][:len(headers)] or len(headers) < 2:
                raise ValueError(f'Workbook {table} columns changed')
        elif first is not None and first != 'Parent':
            tables[table].append([cells.get(f'{excel_column(column)}{number}') for column in range(len(SCHEMAS[table]) + 2)])
    catalogue = catalogue_from_tables(tables)
    overlay_move_labels(catalogue, sheet_cells(parts, paths['Moves']), sheet_cells(parts, paths['Observations']))
    return catalogue


def overlay_move_labels(catalogue, moves, observations):
    # Treat visible move labels and designations as editable authoritative cells.
    # Match the hidden stable ID and current weapon band before applying their values.
    # Sorting or renaming a move cannot transfer its evidence to another identity.
    records = {item['id']: item for item in list(iter_moves(catalogue)) + catalogue['observations']}
    bosses = {item['name']: item['id'] for item in catalogue['bosses']}
    sections = {name: key for key, name in WEAPON_SECTIONS}
    seen = set()
    weapon = None
    identity_column = 'E' if moves.get('C2') == 'Move ID (hex)' else 'H'
    for number in range(1, max(int(re.search(r'\d+$', cell)[0]) for cell in moves) + 1):
        if moves.get(f'A{number}') and moves.get(f'B{number}') is None:
            weapon = sections[moves[f'A{number}']]
        identity = moves.get(f'{identity_column}{number}')
        if identity is None or identity == 'Catalogue ID':
            continue
        if identity in seen:
            raise ValueError(f'Duplicate visible move: {identity}')
        seen.add(identity)
        move = records[identity]
        if bosses[moves[f'A{number}']] != move['boss_id'] or moves[f'C{number}'] != move_source_ids(move):
            raise ValueError(f'{identity}: visible source identity differs from Move data; include hidden IDs when sorting')
        name = moves[f'B{number}']
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f'{identity}: move name must be nonempty text')
        move['name'] = name
        move['weapon'] = weapon
        designation = moves[f'D{number}'].lower()
        if 'designation' in move or designation != 'unclassified':
            move['designation'] = designation
    expected = {item['id'] for item in catalogue['moves'] if item['name_status'] != 'unclassified'}
    if seen != expected:
        raise ValueError('Visible Moves rows differ from the metadata identities; restore missing rows before syncing')
    for number in range(2, max(int(re.search(r'\d+$', cell)[0]) for cell in observations) + 1):
        identity = observations.get(f'I{number}')
        if identity is None:
            continue
        record = records[identity]
        original_name = record.get('name', 'Unclassified')
        if observations[f'B{number}'] != original_name:
            record['name'] = observations[f'B{number}']
        category = record.get('category', record.get('role', 'unclassified'))
        if observations[f'C{number}'] != category.replace('_', ' '):
            record['category'] = observations[f'C{number}'].replace(' ', '_')
        status = record['implementation']['status'] if 'implementation' in record else record['status']
        if observations[f'G{number}'] != status.replace('_', ' '):
            if 'implementation' in record:
                record['implementation']['status'] = observations[f'G{number}'].replace(' ', '_')
            else:
                record['status'] = observations[f'G{number}'].replace(' ', '_')


TUNING_HEADERS = ['Move', 'Field / change', 'Original', 'Current / proposed', 'Mechanism / scope', 'Status']
TUNING_NOTES = [
    'Source action and animation resources stay unchanged.',
    'Byte edits affect private player copies only; proposed values are not active.',
    'Speed changes advance motion and timing together. No animation frames are removed.',
]


def tuning_rows(catalogue):
    # Project documented adaptations into a simple original-versus-current view.
    # Derive speed savings and little-endian bytes from the maintained typed values.
    # Pending targets remain distinct from deployed changes and gameplay verification.
    rows = []
    for move in iter_moves(catalogue):
        adaptation = move.get('adaptation')
        if not adaptation:
            continue
        label = f"{move['name']} ({move['source']['action_id']:X})"
        startup = adaptation.get('startup')
        if startup and startup['multiplier'] != 1:
            start, end, rate = startup['start_frame'], startup['end_frame'], startup['multiplier']
            if end is None or end <= start or rate <= 0 or startup['skip_frames'] or not startup['synchronized_motion_timing']:
                raise ValueError(f"{move['id']}: unsupported shared-clock tuning metadata")
            saved = (end - start) * (1 - 1 / rate)
            rows.append([label, f'Shared clock: frames {start}..{end}', '1x playback rate', f'{rate:g}x playback rate',
                         f'{saved:g} frames shorter in wall-clock time; full motion and timing events retained. No seeking.', startup['status'].replace('_', ' ')])
        if 'source_clip_frames' in adaptation:
            rows.append([label, 'Animation clip length', f"{adaptation['source_clip_frames']} frames", f"{adaptation['clip_frames']} frames",
                         'The complete source animation remains intact.', 'Unchanged' if adaptation['source_clip_frames'] == adaptation['clip_frames'] else 'Changed'])
        for field in adaptation.get('native_fields', []):
            encoding = {'i16le': '<h', 'i8': 'b'}[field['encoding']]
            before = f"{field['original']} ({struct.pack(encoding, field['original']).hex(' ').upper()})"
            after = f"{field['modified']} ({struct.pack(encoding, field['modified']).hex(' ').upper()})"
            current = after if field['applied'] else f'{before}; proposed {after}'
            rows.append([label, f"{field['name']}\n{field['field']} ({field['encoding']})", before, current,
                         field['scope'], field['status'].replace('_', ' ')])
        pulse = adaptation.get('ki_pulse')
        if pulse and 'original_start_frame' in pulse:
            original = 'No player Ki Pulse window' if pulse['original_start_frame'] is None else f"Frame {pulse['original_start_frame']}"
            rows.append([label, 'Native Ki Pulse window', original, f"Frame {pulse['start_frame']}",
                         'Private player recovery uses the native Ki Pulse mechanism.', pulse['status'].replace('_', ' ')])
        for request in adaptation.get('requests', []):
            rows.append([request['scope'], request['feature'], request['original'], request['requested'],
                         request['mechanism'], request['status'].replace('_', ' ')])
    return rows


def replace_tuning(parts, sheet_path, rows):
    # Refresh the adaptation view without creating another metadata authority.
    # Keep its three explanatory lines and authored header while replacing data rows.
    # Ordinary synchronization updates tuning whenever the adaptation records change.
    sheet = ET.fromstring(parts[sheet_path])
    data = sheet.find('m:sheetData', NS)
    styles = row_styles(data, 6, len(TUNING_HEADERS))
    widths = column_widths(sheet, len(TUNING_HEADERS))
    for row in list(data):
        if int(row.attrib['r']) >= 6:
            data.remove(row)
    for number, values in enumerate(rows or [[None] * len(TUNING_HEADERS)], 6):
        append_row(data, number, values, styles, widths)
    dimension = sheet.find('m:dimension', NS)
    if dimension is not None:
        dimension.set('ref', f'A1:F{max(6, len(rows)+5)}')
    parts[sheet_path] = ET.tostring(sheet, encoding='utf-8', xml_declaration=True)


def write_workbook_catalogue(workbook_path, catalogue, downloads_copy=False, template=None):
    # Publish the catalogue and its visible views as one atomic workbook update.
    # Preserve unrelated workbook parts and stage complete files before replacement.
    # A locked or concurrently edited workbook fails without truncating user data.
    validate_catalogue(catalogue)
    workbook_path = Path(workbook_path).resolve()
    source = workbook_path if workbook_path.exists() else Path(template)
    original = source.read_bytes()
    with zipfile.ZipFile(io.BytesIO(original)) as archive:
        entries = archive.infolist()
        parts = {entry.filename: archive.read(entry) for entry in entries}
    workbook = ET.fromstring(parts['xl/workbook.xml'])
    sheets = workbook.find('m:sheets', NS)
    links = workbook_links(parts, 'xl/workbook.xml')
    paths = {sheet.attrib['name']: links[sheet.attrib[f'{{{REL}}}id']] for sheet in sheets}
    required = {'Moves', 'Observations', 'Controls', DATA_SHEET}
    if not required <= set(paths) or set(paths) - required - {'Tuning','Capture occurrences'}:
        raise ValueError('Workbook requires Moves, Observations, Controls, Move data; optional Tuning and Capture occurrences')
    replace_move_sections(parts, paths['Moves'], workbook_sections(catalogue))
    replace_table(parts, paths['Observations'], OBSERVATION_HEADERS, workbook_rows(catalogue)[1])
    if 'Tuning' in paths:
        replace_tuning(parts, paths['Tuning'], tuning_rows(catalogue))
    metadata = ET.fromstring(parts[paths[DATA_SHEET]])
    data = metadata.find('m:sheetData', NS)
    body_style = row_styles(data, 1, 1)[0]
    data.clear()
    rows = data_rows(catalogue_tables(catalogue))
    width = max(map(len, rows))
    for number, row in enumerate(rows, 1):
        append_row(data, number, row, [body_style] * len(row), [36] * len(row), 32)
    dimension = metadata.find('m:dimension', NS)
    if dimension is not None:
        dimension.set('ref', f'A1:{excel_column(width-1)}{len(rows)}')
    parts[paths[DATA_SHEET]] = ET.tostring(metadata, encoding='utf-8', xml_declaration=True)
    for sheet in sheets:
        if sheet.attrib['name'] == DATA_SHEET:
            sheet.set('state', 'hidden')
    parts['xl/workbook.xml'] = ET.tostring(workbook, encoding='utf-8', xml_declaration=True)
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, 'w') as archive:
        for entry in entries:
            archive.writestr(entry, parts[entry.filename])
    targets = [workbook_path]
    if downloads_copy is not False:
        download = Path(downloads_copy or Path.home() / 'Downloads' / FILENAME).resolve()
        if download != workbook_path:
            targets.append(download)
    staged = []
    try:
        for target in targets:
            handle, name = tempfile.mkstemp(dir=target.parent, suffix='.xlsx.tmp')
            staged.append((target, Path(name)))
            with os.fdopen(handle, 'wb') as stream:
                stream.write(payload.getvalue())
        if source.read_bytes() != original:
            raise OSError('Workbook changed during synchronization; retry')
        for target, temporary in staged:
            os.replace(temporary, target)
    finally:
        for target, temporary in staged:
            temporary.unlink(missing_ok=True)
    return tuple(targets)


def sync_workbook(catalogue_path=None, workbook_path=None, downloads_copy=None):
    # Refresh visible sections from the workbook's editable technical cells.
    # Read current visible labels first, then publish matching repository and Downloads copies.
    # Synchronization never needs a second maintained metadata file.
    source = Path(catalogue_path or Path(__file__).resolve().parents[1] / 'outputs' / FILENAME)
    catalogue = load_catalogue(source)
    return write_workbook_catalogue(workbook_path or source, catalogue, downloads_copy, source)
