from copy import deepcopy
import json
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from catalogue import load_catalogue, save_catalogue
from catalogue.spreadsheet_sync import sync_workbook, workbook_sections, workbook_rows, MOVE_HEADERS, FILENAME, NS


class SpreadsheetSyncTests(unittest.TestCase):
    def setUp(self):
        # Copy the maintained catalogue and workbook into a temporary repository layout.
        # Register directory cleanup and use a separate fake Downloads destination.
        # Workbook regeneration tests must never overwrite the user's actual spreadsheet copies.
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder=Path(temporary.name)
        (self.folder/'catalogue').mkdir()
        (self.folder/'outputs').mkdir()
        self.catalogue=load_catalogue()
        self.workbook=self.folder/'outputs'/FILENAME
        self.catalogue_path=self.workbook
        shutil.copyfile(ROOT/'outputs'/FILENAME,self.workbook)
        self.downloads=self.folder/'downloads.xlsx'

    def test_named_move_is_literal_and_all_observations_survive(self):
        # Preserve literal move names and every classified or unknown observation.
        # Synchronize a move name beginning with formula syntax and inspect all observation rows.
        # Workbook text must remain literal while raw capture records stay intact.
        self.catalogue['moves'][0]['name']='=Literal move name'
        save_catalogue(self.catalogue_path, self.catalogue)
        self.assertEqual(sync_workbook(self.catalogue_path,downloads_copy=self.downloads),
                         (self.workbook,self.downloads))
        self.assertEqual(self.workbook.read_bytes(),self.downloads.read_bytes())
        with zipfile.ZipFile(self.workbook) as archive:
            moves=ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
            observed=ET.fromstring(archive.read('xl/worksheets/sheet2.xml'))
        cell=moves.find('m:sheetData/m:row/m:c[@r="B3"]',NS)
        self.assertEqual(cell.attrib['t'],'inlineStr')
        self.assertEqual(cell.find('m:is/m:t',NS).text,'=Literal move name')
        self.assertIsNone(cell.find('m:f',NS))
        ids=[cell.find('m:is/m:t',NS).text for cell in observed.findall('m:sheetData/m:row/m:c',NS)
             if cell.attrib['r'].startswith('I') and cell.attrib['r']!='I1']
        expected=self.catalogue['observations']+[item for item in self.catalogue['moves'] if item['name_status']=='unclassified']
        self.assertEqual(ids,[item['id'] for item in expected])

    def test_non_sword_or_unclassified_move_cannot_be_published(self):
        # Keep the maintained workbook restricted to curated sword identities.
        # Try an unknown weapon and a classified non-sword weapon before publication.
        # Invalid edits must leave the original workbook and Downloads untouched.
        original=self.workbook.read_bytes()
        for weapon in (None, 'spear'):
            self.catalogue['moves'][0]['weapon']=weapon
            with self.assertRaisesRegex(ValueError, 'sword data only'):
                save_catalogue(self.workbook,self.catalogue)
            self.assertEqual(self.workbook.read_bytes(),original)
            self.assertFalse(self.downloads.exists())

    def test_populated_sword_sections_grow_shrink_and_keep_source_groups(self):
        # Regenerate only populated weapon sections as their sizes and membership change.
        # Add and remove populated weapon groups across repeated synchronization.
        # The primary sheet must regenerate section geometry without accumulating empty templates.
        named=[deepcopy(item) for item in self.catalogue['moves'] if item['name_status']!='unclassified'][:3]
        self.catalogue['moves']=named
        for count in (1,3,2):
            self.catalogue['moves']=named[:count]
            save_catalogue(self.catalogue_path, self.catalogue)
            sync_workbook(self.catalogue_path,downloads_copy=False)
            with zipfile.ZipFile(self.workbook) as archive:
                sheet=ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
            self.assertIsNone(sheet.find('m:tableParts',NS))
            expected_merges=[]
            number=1
            for section in workbook_sections(self.catalogue):
                expected_merges.append(f'A{number}:G{number}')
                banner=sheet.find(f'm:sheetData/m:row/m:c[@r="A{number}"]/m:is/m:t',NS)
                self.assertEqual(banner.text,section['name'])
                headers=sheet.findall(f'm:sheetData/m:row[@r="{number+1}"]/m:c/m:is/m:t',NS)
                self.assertEqual([value.text for value in headers],MOVE_HEADERS)
                for row in sheet.findall(f'm:sheetData/m:row[@r="{number+2}"]',NS):
                    self.assertEqual(len(row),8)
                number+=3+len(section['rows'])
            self.assertEqual([item.attrib['ref'] for item in sheet.find('m:mergeCells',NS)],expected_merges)
            self.assertEqual(max(int(row.attrib['r']) for row in sheet.find('m:sheetData',NS)),number-2)
            dimension=sheet.find('m:dimension',NS)
            if dimension is not None:
                self.assertEqual(dimension.attrib['ref'],f'A1:H{number-2}')
            first=self.workbook.read_bytes()
            sync_workbook(self.catalogue_path,downloads_copy=False)
            self.assertEqual(first,self.workbook.read_bytes())

    def test_repeat_empty_catalogue_and_same_destination_are_stable(self):
        # Keep empty-catalogue synchronization deterministic at the same destination.
        # Repeat sync with no moves and with the destination equal to the canonical workbook.
        # Empty sections and repeated writes must retain deterministic valid workbook structure.
        self.catalogue['moves']=[]
        save_catalogue(self.catalogue_path, self.catalogue)
        self.assertEqual(sync_workbook(self.catalogue_path,downloads_copy=self.workbook),(self.workbook,))
        first=self.workbook.read_bytes()
        sync_workbook(self.catalogue_path,downloads_copy=self.workbook)
        self.assertEqual(first,self.workbook.read_bytes())

    def test_invalid_catalogue_leaves_both_copies_unchanged(self):
        # Leave workbook copies unchanged when the catalogue is invalid.
        # Supply invalid catalogue data before synchronizing the canonical and Downloads copies.
        # Validation failure must occur before either user's workbook is replaced.
        before=self.workbook.read_bytes()
        self.catalogue['moves'][0]['source']['address']='0x123'
        with self.assertRaises(ValueError):
            save_catalogue(self.catalogue_path, self.catalogue)
        self.assertEqual(before,self.workbook.read_bytes())
        self.assertFalse(self.downloads.exists())

    def test_locked_copy_raises_and_retains_previous_download(self):
        # Preserve the previous Downloads copy when replacement is blocked by Excel.
        # Fail only the final Downloads replacement after successful canonical regeneration.
        # The prior user copy must remain intact and the incomplete synchronization must be visible.
        self.downloads.write_bytes(b'previous')
        import catalogue.spreadsheet_sync as module
        replace=module.os.replace
        def locked(source,target):
            # Reject only replacement of the fixture's Downloads workbook.
            # Allow catalogue-side replacement through the original os.replace call.
            # A locked user copy must preserve its previous bytes and surface the sync failure.
            if Path(target)==self.downloads:
                raise PermissionError('Workbook locked')
            replace(source,target)
        with patch.object(module.os,'replace',side_effect=locked), self.assertRaises(PermissionError):
            sync_workbook(self.catalogue_path,downloads_copy=self.downloads)
        self.assertEqual(self.downloads.read_bytes(),b'previous')
        self.assertFalse(list(self.folder.rglob('*.tmp')))

    def edit_cell(self, sheet_name, address, value):
        # Modify a literal cell in the private workbook as an Excel edit would.
        # Resolve the actual worksheet relationship and preserve every unrelated ZIP entry.
        # Authority tests then exercise edited workbook bytes rather than Python dictionaries.
        from catalogue.spreadsheet_sync import MAIN, REL, workbook_links
        with zipfile.ZipFile(self.workbook) as archive:
            entries = archive.infolist()
            parts = {entry.filename: archive.read(entry) for entry in entries}
        sheets = ET.fromstring(parts['xl/workbook.xml']).find('m:sheets', NS)
        selected = next(sheet for sheet in sheets if sheet.attrib['name'] == sheet_name)
        path = workbook_links(parts, 'xl/workbook.xml')[selected.attrib[f'{{{REL}}}id']]
        sheet = ET.fromstring(parts[path])
        cell = next(cell for cell in sheet.findall('m:sheetData/m:row/m:c', NS) if cell.attrib['r'] == address)
        cell.clear()
        cell.attrib.update(r=address, t='inlineStr')
        ET.SubElement(ET.SubElement(cell, f'{{{MAIN}}}is'), f'{{{MAIN}}}t').text = value
        parts[path] = ET.tostring(sheet, encoding='utf-8', xml_declaration=True)
        with zipfile.ZipFile(self.workbook, 'w') as archive:
            for entry in entries:
                archive.writestr(entry, parts[entry.filename])

    def test_visible_edit_is_authoritative_and_import_name_follows_it(self):
        # Use the visible move name as the engine's display-name authority.
        # Edit the workbook cell, resolve an import manifest, and synchronize both workbook copies.
        # Source signatures, bindings and every retained evidence record must survive unchanged.
        sys.path.insert(0, str(ROOT/'runtime'))
        from move_imports import read_import_manifest
        self.edit_cell('Moves', 'B3', 'Edited in the spreadsheet')
        loaded = load_catalogue(self.workbook)
        expected = deepcopy(self.catalogue)
        expected['moves'][0]['name'] = 'Edited in the spreadsheet'
        self.assertEqual(loaded, expected)
        loaded['moves'][0]['name'] = 'Discarded caller mutation'
        self.assertEqual(load_catalogue(self.workbook), expected)
        manifest = read_import_manifest(ROOT/'catalogue/imports/okatsu.json', self.workbook)
        self.assertEqual(manifest['moves'][0]['name'], 'Edited in the spreadsheet')
        sync_workbook(self.workbook, downloads_copy=self.downloads)
        self.assertEqual(load_catalogue(self.downloads), expected)

    def test_broken_evidence_parent_is_rejected_before_publication(self):
        # Reject a detached evidence row rather than silently discarding its provenance.
        # Change one normalized evidence parent ID in the temporary workbook.
        # Synchronization must leave both files untouched when a required relation cannot resolve.
        from catalogue.spreadsheet_sync import REL, workbook_links, sheet_cells
        with zipfile.ZipFile(self.workbook) as archive:
            parts = {name: archive.read(name) for name in archive.namelist()}
        sheets = ET.fromstring(parts['xl/workbook.xml']).find('m:sheets', NS)
        selected = next(sheet for sheet in sheets if sheet.attrib['name'] == 'Move data')
        path = workbook_links(parts, 'xl/workbook.xml')[selected.attrib[f'{{{REL}}}id']]
        cells = sheet_cells(parts, path)
        marker = next(int(address[1:]) for address, value in cells.items() if address.startswith('A') and value == 'Evidence')
        self.edit_cell('Move data', f'A{marker+2}', 'detached/evidence')
        before = self.workbook.read_bytes()
        with self.assertRaises(KeyError):
            sync_workbook(self.workbook, downloads_copy=self.downloads)
        self.assertEqual(self.workbook.read_bytes(), before)
        self.assertFalse(self.downloads.exists())

    def test_partial_row_sort_cannot_reassign_source_evidence(self):
        # Keep stable move IDs tied to their recorded boss and action identities.
        # Simulate sorting visible cells without moving the hidden stable-ID column.
        # Loading must reject mismatched identity instead of assigning another move's evidence.
        self.edit_cell('Moves', 'C3', '0C66h')
        with self.assertRaisesRegex(ValueError, 'visible source identity differs'):
            load_catalogue(self.workbook)

    def test_tuning_keeps_pending_bytes_distinct_from_deployed_changes(self):
        # Keep proposed private-copy bytes distinct from the currently applied value.
        # Save a pending launch change, inspect its view, then mark the same fixture deployed.
        # Source bytes and evidence must remain identical through both publication states.
        from catalogue.spreadsheet_sync import tuning_rows
        move = next(item for item in self.catalogue['moves'] if item['id'] == 'jin_hayabusa.action_0c79')
        source, evidence = deepcopy(move['source']), deepcopy(move['evidence'])
        field = next(item for item in move['adaptation']['native_fields'] if item['field'] == 'combat row +0x17')
        field['applied'] = False
        field['status'] = 'pending_implementation_not_deployed'
        save_catalogue(self.workbook, self.catalogue)
        loaded = load_catalogue(self.workbook)
        pending = next(row for row in tuning_rows(loaded) if 'combat row +0x17' in row[1])
        self.assertEqual(pending[2], '12 (0C)')
        self.assertEqual(pending[3], '12 (0C); proposed 16 (10)')
        field['applied'] = True
        field['status'] = 'deployed_live_validation_pending'
        save_catalogue(self.workbook, self.catalogue)
        loaded = load_catalogue(self.workbook)
        current = next(row for row in tuning_rows(loaded) if 'combat row +0x17' in row[1])
        self.assertEqual(current[2], '12 (0C)')
        self.assertEqual(current[3], '16 (10)')
        stored = next(item for item in loaded['moves'] if item['id'] == move['id'])
        self.assertEqual(stored['source'], source)
        self.assertEqual(stored['evidence'], evidence)
        before = self.workbook.read_bytes()
        field['modified'] = 128
        with self.assertRaises(struct.error):
            save_catalogue(self.workbook, self.catalogue)
        self.assertEqual(self.workbook.read_bytes(), before)

    def test_decoded_source_rows_keep_full_flags_and_capture_identity(self):
        # Preserve decoded source rows without rounding full-width combat flags.
        # Round-trip signed windows, byte values, raw row evidence and a stable capture hash.
        # Workbook storage must not collapse later decoding into a new or lossy encounter.
        source = self.catalogue['moves'][0]['source']
        source.update(cancel_frame=-1, ki_pulse_percent=40, ki_pulse_start=60, ki_pulse_fill=25, ki_pulse_hold=24,
            transition_rows_total=130, transition_rows_omitted=2, combat_rows_total=17, combat_rows_omitted=1,
            transition_links=[{'row_index':0, 'target_action_id':0x361, 'kind':'paired_contact',
                'conditions':[22,-1,-1,-1,-1], 'mode':2, 'input_id':-1, 'selectors':[255]*8,
                'target_options':[0]*6, 'flags':0xffffffff, 'window_frames':[-32768,32767], 'raw_hex':'00'*48}],
            combat_rows=[{'row_index':0, 'flags':'0x0800000000000080', 'ground_horizontal':-12,
                'ground_vertical':12, 'air_horizontal':0, 'air_vertical':12, 'raw_hex':'00'*32}])
        self.catalogue['encounters'][0]['source_sha256'] = 'a'*64
        save_catalogue(self.workbook, self.catalogue)
        loaded = load_catalogue(self.workbook)
        self.assertEqual(loaded['moves'][0]['source'], source)
        self.assertEqual(loaded['encounters'][0]['source_sha256'], 'a'*64)
        self.assertIsInstance(loaded['moves'][0]['source']['combat_rows'][0]['flags'], str)
