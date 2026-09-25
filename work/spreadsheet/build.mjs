import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';

const root = path.resolve(import.meta.dirname, '../..');
const logName = 'sword-living-weapon-take1.jsonl';
const source = (await fs.readFile(path.join(root, 'work', logName), 'utf8')).trim().split(/\r?\n/).map((line, i) => ({...JSON.parse(line), sourceLine: i + 1}));
const config = JSON.parse(await fs.readFile(path.join(root, 'work/player-action-candidate.json'), 'utf8'));
const status = JSON.parse(await fs.readFile(path.join(root, 'work/sword-living-weapon-take1-status.json'), 'utf8'));
const object = config.candidates[0].object;
const records = source.filter(x => x.kind === 'action_state' && x.object === object);
const labels = new Map([
  ...Array.from({length: 5}, (_, i) => [0xCF0+i, `Low quick candidate ${i+1}`]),
  [0xCF5, 'First low heavy candidate'],
  ...Array.from({length: 6}, (_, i) => [0xD34+i, `LW quick candidate ${i+1}`]),
  [0xD4D, 'LW heavy preparation candidate'],
  [0xD3A, 'LW heavy candidate'],
  [0xD4E, 'Quadrisect / held-heavy candidate'],
]);
const groups = new Map();
let lastPointer;
let pointerEntries = 0;
for (const record of records) {
  record.recordEntry = record.current !== lastPointer;
  pointerEntries += Number(record.recordEntry);
  lastPointer = record.current;
  assert.equal(typeof record.descriptor?.word0, 'number');
  const key = record.current;
  if (!groups.has(key)) groups.set(key, []);
  groups.get(key).push(record);
}
assert.equal(source.filter(x => x.kind === 'input').length, 0);
assert.equal(records.length, 126);
assert.equal(groups.size, 32);
const observations = [...groups.values()].sort((a,b) => a[0].descriptor.word0 - b[0].descriptor.word0);
for (const group of observations) {
  assert.equal(new Set(group.map(x => x.descriptor.word0)).size, 1);
  assert.equal(new Set(group.map(x => x.index)).size, 1);
  assert.equal(new Set(group.map(x => x.descriptor.payload)).size, 1);
}
const hex = n => `0x${n.toString(16).toUpperCase().padStart(4, '0')}`;
const workbook = Workbook.create();
const catalog = workbook.worksheets.add('Move observations');
const evidence = workbook.worksheets.add('State evidence');
const color = {ink: '#243247', muted: '#54657C', navy: '#253B5B', pale: '#F3F6FA', line: '#CED7E3'};

function base(sheet, range) {
  sheet.showGridLines = false;
  sheet.getRange(range).format.font = {name: 'Arial', size: 10, color: color.ink};
  sheet.getRange(range).format.rowHeight = 21;
  sheet.getRange(range).format.verticalAlignment = 'center';
  sheet.getRange(range).format.horizontalAlignment = 'left';
  sheet.tabColor = color.navy;
}
function heading(sheet, title, lastColumn) {
  sheet.getRange('A2').values = [[title]];
  sheet.getRange('A2').format.font = {name: 'Arial', size: 14, bold: true, color: color.navy};
  sheet.getRange('A2').format.rowHeight = 29;
  sheet.getRange(`A2:${lastColumn}2`).format.borders = {bottom:{style:'thin', color:color.line}};
}
function table(sheet, row, headers, data, name) {
  const lastColumn = String.fromCharCode(64 + headers.length);
  sheet.getRange(`A${row}:${lastColumn}${row}`).values = [headers];
  sheet.getRange(`A${row+1}:${lastColumn}${row+data.length}`).values = data;
  const t = sheet.tables.add(`A${row}:${lastColumn}${row+data.length}`, true, name);
  t.showFilterButton = true;
  const h = sheet.getRange(`A${row}:${lastColumn}${row}`);
  h.format.fill = color.navy;
  h.format.font = {name:'Arial',size:10,bold:true,color:'#FFFFFF'};
  h.format.horizontalAlignment = 'center';
  h.format.rowHeight = 30;
  h.format.borders = {insideVertical: {style:'thin',color:'#FFFFFF'}};
  for(let i=0;i<data.length;i++) {
    sheet.getRange(`A${row+1+i}:${lastColumn}${row+1+i}`).format.fill = i%2 ? color.pale : '#FFFFFF';
  }
  sheet.freezePanes.freezeRows(row);
  return row + data.length;
}

base(catalog, 'A1:L42');
heading(catalog, 'Nioh 1 sword move observations', 'L');
catalog.getRange('A3').values = [['Word0 = unsigned 16-bit value at descriptor +0x00. Full action-ID meaning is unproven.']];
catalog.getRange('A4').values = [['Labels are provisional from sequence timing. This take contains no physical button events.']];
catalog.getRange('A5').values = [['Low quick strings had variable lengths. Only the first low heavy is mapped; additional heavies remain unmapped.']];
catalog.getRange('A6').values = [[`${groups.size} unique records; ${records.length} state events; ${pointerEntries} record entries including the initial state. LW = Living Weapon.`]];
catalog.getRange('A7').values = [['Times are sampled session seconds, not animation frames. Addresses apply only to this process session.']];
catalog.getRange('A3:L7').format.font = {name:'Arial',size:10,color:color.muted};
const catRows = observations.map(group => {
  const first = group[0], last = group.at(-1), word = first.descriptor.word0;
  return [hex(word), word, labels.get(word) ?? 'Unmapped', labels.has(word) ? 'Provisional' : 'Unmapped', first.index, first.t, last.t, group.length, group.filter(r=>r.recordEntry).length, first.current, first.descriptor.payload, labels.has(word) ? 'User sequence timing' : 'No move label established'];
});
const catEnd = table(catalog, 9, ['Word0 (hex)','Word0 (decimal)','Candidate move','Label status','Object index','First event (s)','Last event (s)','State events','Record entries','Descriptor ptr (session)','Payload ptr (session)','Label basis'], catRows, 'MoveObservationCatalog');
const widths = [15,18,39,17,16,18,18,16,18,25,25,29];
widths.forEach((w,i)=>catalog.getRangeByIndexes(0,i,catEnd,1).format.columnWidth=w);
for (const col of ['B','E','H','I']) {catalog.getRange(`${col}10:${col}${catEnd}`).setNumberFormat('0');catalog.getRange(`${col}10:${col}${catEnd}`).format.horizontalAlignment='right';}
for (const col of ['F','G']) {catalog.getRange(`${col}10:${col}${catEnd}`).setNumberFormat('0.000');catalog.getRange(`${col}10:${col}${catEnd}`).format.horizontalAlignment='right';}
catalog.getRange(`A10:A${catEnd}`).setNumberFormat('@');
catalog.getRange(`J10:K${catEnd}`).setNumberFormat('@');

base(evidence, `A1:M${records.length+9}`);
heading(evidence, 'Recorded state evidence', 'M');
evidence.getRange('A3').values = [[`Source: ${logName}. Selected object: ${object}. PID: ${config.pid}.`]];
evidence.getRange('A4').values = [['Object selected by correlation with the user sequence. Player ownership is not independently established.']];
evidence.getRange('A5').values = [['All selected-object state events are preserved. A new record entry means the current descriptor pointer changed.']];
evidence.getRange('A6').values = [[`Read-only capture: ${status.seconds} s; ${status.samples.toLocaleString('en-US')} polls; 10 ms requested interval; ${status.max_sample_gap_ms} ms maximum observed gap; ${status.read_failures} read failures.`]];
evidence.getRange('A7').values = [['First and last catalog times are event timestamps, not dwell duration. State snapshots are not atomic.']];
evidence.getRange('A3:M7').format.font = {name:'Arial',size:10,color:color.muted};
const evRows = records.map((r,i)=>[i+1, r.t, hex(r.descriptor.word0), r.descriptor.word0, r.index, r.current, r.previous, r.previous_index, r.pending, r.counter, r.descriptor.payload, r.recordEntry ? 'Yes' : 'No', r.sourceLine]);
const evEnd = table(evidence, 9, ['Event','Time (s)','Word0 (hex)','Word0 (decimal)','Object index','Current descriptor ptr','Previous descriptor ptr','Previous index','Pending ptr','Counter (+0xDC)','Payload ptr (+0x20)','New record entry','Source line'],evRows,'StateEvidence');
[10,15,15,18,16,25,26,18,24,21,25,22,15].forEach((w,i)=>evidence.getRangeByIndexes(0,i,evEnd,1).format.columnWidth=w);
for(const col of ['A','D','E','H','J','M']) {evidence.getRange(`${col}10:${col}${evEnd}`).setNumberFormat('0');evidence.getRange(`${col}10:${col}${evEnd}`).format.horizontalAlignment='right';}
evidence.getRange(`B10:B${evEnd}`).setNumberFormat('0.000');
evidence.getRange(`B10:B${evEnd}`).format.horizontalAlignment='right';
for(const col of ['C','F','G','I','K']) evidence.getRange(`${col}10:${col}${evEnd}`).setNumberFormat('@');
// Counts stay traceable to the preserved state observations.
catalog.getRange(`H10:H${catEnd}`).formulas = catRows.map((_,i)=>[`=COUNTIFS('State evidence'!$F$10:$F$${evEnd},J${i+10})`]);
catalog.getRange(`I10:I${catEnd}`).formulas = catRows.map((_,i)=>[`=COUNTIFS('State evidence'!$F$10:$F$${evEnd},J${i+10},'State evidence'!$L$10:$L$${evEnd},"Yes")`]);
workbook.recalculate();
// Verify count formulas react to a source edit, then restore every original value.
const originalPointer = evidence.getRange('F10').values[0][0];
const originalCount = catalog.getRange('H10:I10').values[0];
evidence.getRange('F10').values = [['unmatched-verification-pointer']];
workbook.recalculate();
assert.deepEqual(catalog.getRange('H10:I10').values[0], [originalCount[0]-1, originalCount[1]-1]);
evidence.getRange('F10').values = [[originalPointer]];
workbook.recalculate();
const counts = catalog.getRange(`H10:I${catEnd}`).values;
for(let i=0;i<counts.length;i++) assert.deepEqual(counts[i],catRows[i].slice(7,9));
assert.equal(counts.reduce((n,x)=>n+x[0],0),126);
assert.equal(counts.reduce((n,x)=>n+x[1],0),pointerEntries);
const inspect = await workbook.inspect({kind:'table',range:'Move observations!A9:L14',include:'values,formulas',tableMaxRows:6,tableMaxCols:12,maxChars:5500});
const errors = await workbook.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:100},summary:'final formula error scan'});
await fs.writeFile(path.join(import.meta.dirname,'verification.txt'),`${inspect.ndjson}\n${errors.ndjson}\n`);
for(const [sheetName,range,file] of [
  ['Move observations','A1:L24','catalog-preview.png'],
  ['Move observations','A25:L41','catalog-tail-preview.png'],
  ['State evidence','A1:M20','evidence-preview.png'],
  ['State evidence','A103:M135','evidence-tail-preview.png']
]) {
  const preview=await workbook.render({sheetName,range,scale:1,format:'png'});
  await fs.writeFile(path.join(import.meta.dirname,file),new Uint8Array(await preview.arrayBuffer()));
}
await fs.mkdir(path.join(root,'outputs'),{recursive:true});
const file=path.join(root,'outputs/Nioh1-Sword-Move-Observations.xlsx');
const xlsx=await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(file);
await fs.rename(`${file}.inspect.ndjson`, path.join(import.meta.dirname, 'export-inspection.ndjson')).catch(error => { if(error.code !== 'ENOENT') throw error; });
console.log(JSON.stringify({file,records:records.length,uniqueRecords:groups.size,recordEntries:pointerEntries,provisionalLabels:labels.size,unmapped:groups.size-labels.size,errors:errors.ndjson}));
