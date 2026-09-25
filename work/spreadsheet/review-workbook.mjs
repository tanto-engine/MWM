import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {FileBlob, SpreadsheetFile} from '@oai/artifact-tool';

const root = path.resolve(import.meta.dirname, '../..');
const file = process.env.NIOH_WORKBOOK || path.join(root, 'outputs/Nioh1-Sword-Move-Observations.xlsx');
const python = path.join(process.env.USERPROFILE, '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe');
const data = JSON.parse(execFileSync(python, ['-c', 'import json; from catalogue.catalogue import load_catalogue; from catalogue.spreadsheet_sync import workbook_sections, workbook_rows, MOVE_HEADERS, OBSERVATION_HEADERS, tuning_rows, TUNING_HEADERS, TUNING_NOTES; c=load_catalogue(); print(json.dumps(dict(sections=workbook_sections(c), headers=MOVE_HEADERS, observations=workbook_rows(c)[1], observation_headers=OBSERVATION_HEADERS, tuning=tuning_rows(c), tuning_headers=TUNING_HEADERS, tuning_notes=TUNING_NOTES)))'], {cwd: root, encoding: 'utf8'}));
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(file));
const moves = workbook.worksheets.getItem('Moves');
let tuningSheet;
for (const sheet of workbook.worksheets.items) {
  if (sheet.name === 'Tuning') tuningSheet = sheet;
}
if (process.argv.includes('--tuning-layout')) {
  const sheet = tuningSheet || workbook.worksheets.add('Tuning');
  sheet.getUsedRange()?.unmerge();
  sheet.getUsedRange()?.clear({applyTo: 'all'});
  const area = sheet.getRangeByIndexes(0, 0, Math.max(6, data.tuning.length + 5), 6);
  area.format.font = {name: 'Arial', size: 11, color: '#202020'};
  area.format.wrapText = true;
  area.format.verticalAlignment = 'center';
  area.format.rowHeight = 64;
  for (const [index, note] of data.tuning_notes.entries()) {
    const line = sheet.getRangeByIndexes(index, 0, 1, 6);
    line.merge();
    line.values = [[note]];
    line.format.rowHeight = 28;
    line.format.fill = '#DFE8E6';
  }
  sheet.getRange('A4:F4').format.rowHeight = 12;
  sheet.getRange('A5:F5').values = [data.tuning_headers];
  sheet.getRange('A5:F5').format.fill = '#F2F2F2';
  sheet.getRange('A5:F5').format.font = {name: 'Arial', size: 11, bold: true};
  sheet.getRange('A5:F5').format.rowHeight = 30;
  sheet.getRangeByIndexes(5, 0, Math.max(1, data.tuning.length), 6).values = data.tuning.length ? data.tuning : [[null, null, null, null, null, null]];
  for (const [index, width] of [27, 30, 26, 33, 60, 38].entries()) {
    sheet.getRangeByIndexes(0, index, data.tuning.length + 5, 1).format.columnWidth = width;
  }
  sheet.freezePanes.freezeRows(5);
  sheet.showGridLines = false;
  workbook.recalculate();
  await (await SpreadsheetFile.exportXlsx(workbook)).save(file);
  console.log('Tuning layout saved from catalogue adaptation metadata.');
  process.exit(0);
}
if (process.argv.includes('--before')) {
  const preview = await workbook.render({sheetName: 'Moves', range: 'A1:G12', scale: 1, format: 'png'});
  await fs.writeFile(path.join(import.meta.dirname, 'before-jin-update.png'), new Uint8Array(await preview.arrayBuffer()));
  process.exit(0);
}
const controlSheet = workbook.worksheets.getItem('Controls');
workbook.recalculate();
let offset = 0;
for (const section of data.sections) {
  assert.equal(moves.getRangeByIndexes(offset, 0, 1, 1).values[0][0], section.name);
  assert.deepEqual(moves.getRangeByIndexes(offset + 1, 0, section.rows.length + 1, 7).values, [data.headers, ...section.rows]);
  const preview = await workbook.render({sheetName: 'Moves', range: 'A' + (offset + 1) + ':G' + Math.min(offset + section.rows.length + 2, offset + 12), scale: 1, format: 'png'});
  await fs.writeFile(path.join(import.meta.dirname, 'moves-' + (section.key || 'unclassified') + '.png'), new Uint8Array(await preview.arrayBuffer()));
  offset += section.rows.length + 3;
}
const observations = workbook.worksheets.getItem('Observations');
assert.deepEqual(observations.getRangeByIndexes(0, 0, data.observations.length + 1, 9).values, [data.observation_headers, ...data.observations]);
const preview = await workbook.render({sheetName: 'Observations', range: 'A1:I6', scale: 1, format: 'png'});
await fs.writeFile(path.join(import.meta.dirname, 'observations.png'), new Uint8Array(await preview.arrayBuffer()));
if (controlSheet) {
  const controlPreview = await workbook.render({sheetName: 'Controls', range: 'A33:D46', scale: 1, format: 'png'});
  await fs.writeFile(path.join(import.meta.dirname, 'controls.png'), new Uint8Array(await controlPreview.arrayBuffer()));
}
if (tuningSheet) {
  assert.deepEqual(tuningSheet.getRangeByIndexes(4, 0, data.tuning.length + 1, 6).values, [data.tuning_headers, ...data.tuning]);
  for (const [index, note] of data.tuning_notes.entries()) assert.equal(tuningSheet.getRangeByIndexes(index, 0, 1, 1).values[0][0], note);
  const tuningPreview = await workbook.render({sheetName: 'Tuning', range: 'A1:F' + (data.tuning.length + 5), scale: 1, format: 'png'});
  await fs.writeFile(path.join(import.meta.dirname, 'tuning.png'), new Uint8Array(await tuningPreview.arrayBuffer()));
}
const errors = await workbook.inspect({kind: 'match', searchTerm: '#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!', options: {useRegex: true, maxResults: 20}, summary: 'Formula error scan'});
await fs.writeFile(path.join(import.meta.dirname, 'catalogue-verification.txt'), errors.ndjson);
const counts = [];
for (const section of data.sections) counts.push([section.name, section.rows.length]);
console.log(JSON.stringify({sections: counts, observations: data.observations.length}));
