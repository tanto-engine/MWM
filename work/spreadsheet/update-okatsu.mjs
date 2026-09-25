import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';

const root = path.resolve(import.meta.dirname, '../..');
const file = path.join(root, 'outputs/Nioh1-Sword-Move-Observations.xlsx');
const backup=path.join(import.meta.dirname,'before-okatsu.xlsx');
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(file));
if (process.argv.includes('--inspect')) {
  console.log((await workbook.inspect({kind:'workbook,sheet,table',maxChars:4000,tableMaxRows:3,tableMaxCols:5})).ndjson);
  console.log((await workbook.inspect({kind:'table',range:'Move observations!A30:L41',include:'values,formulas',maxChars:3500,tableMaxRows:12,tableMaxCols:5})).ndjson);
  const preview = await workbook.render({sheetName:'Move observations',range:'A1:L14',scale:1,format:'png'});
  await fs.writeFile(path.join(import.meta.dirname,'before-okatsu.png'),new Uint8Array(await preview.arrayBuffer()));
  process.exit(0);
}
const saved = ['Move observations','State evidence'].map(name => {
  const sheet=workbook.worksheets.getItem(name), range=sheet.getUsedRange();
  return {name, values:range.values, formulas:range.formulas};
});
const findings = JSON.parse(await fs.readFile(path.join(root,'outputs/okatsu-prototype/findings.json'),'utf8'));
assert.equal(findings.target.motion_key,1220);
assert.equal(findings.charged_target.motion_key,1230);
assert.equal(findings.controller.hold_seconds,.25);
const capture=(await fs.readFile(path.join(root,'outputs/Okatsu-Capture-30s/events.jsonl'),'utf8')).trim().split(/\r?\n/).map(JSON.parse);
const states=capture.filter(e=>e.kind==='action_state' && e.role==='boss_candidate');
const metadata=new Map(capture.filter(e=>e.kind==='metadata' && e.role==='boss_candidate').map(e=>[e.word0_u16,e]));
const stateCounts=new Map(),entryCounts=new Map();
let previous;
for(const s of states) {
  const key=s.descriptor.word0_u16;
  stateCounts.set(key,(stateCounts.get(key)||0)+1);
  if(s.current!==previous) entryCounts.set(key,(entryCounts.get(key)||0)+1);
  previous=s.current;
}
const hex=n=>n.toString(16).toUpperCase().padStart(4,'0');
const known=[
  [0xC64,'Charged Rush','Sword',1220,'LB + Circle: tap/release','Player use confirmed',28,'Capture; port'],
  [0xC66,'Leaping Slash','Sword',1230,'LB + Circle: hold 0.25 s','Player use confirmed',22,'Profile; port'],
];
const other=[0xC54,0xC55,0xC5E,0xC61,0xC62,0xC63,0xC65,0xC69].map(key=> {
  const m=metadata.get(key),payload=Buffer.from(m.payload_prefix.bytes,'hex');
  assert.equal(payload.readInt16LE(0x34),-1);
  return [key,'Unidentified action','Unverified',payload.readInt32LE(0x20),'Unassigned','Captured only',m.transition_slice.count,'Capture'];
});
const rows=[...known,...other].map(([key,name,weapon,motion,binding,status,transitions,source])=>
  [hex(key),key,name,weapon,motion,motion,binding,status,entryCounts.get(key)||0,stateCounts.get(key)||0,transitions,source]);
assert.equal(rows[0][8],4); assert.equal(rows[1][8],0);
let sheet;
try { sheet=workbook.worksheets.getItem('Okatsu sword'); } catch {}
if (!sheet) sheet=workbook.worksheets.add('Okatsu sword');
else {
  for (const table of [...sheet.tables.items]) table.delete();
  sheet.getUsedRange().clear({applyTo:'all'});
}
sheet.showGridLines=false; sheet.tabColor='#253B5B';
const body=sheet.getRange('A1:L38');
body.format.font={name:'Arial',size:10,color:'#243247'};
body.format.rowHeight=21;body.format.verticalAlignment='center';body.format.horizontalAlignment='left';
[16,16,30,18,14,14,34,28,18,18,19,20].forEach((width,i)=>sheet.getRangeByIndexes(0,i,38,1).format.columnWidth=width);
sheet.getRange('A2').values=[['Okatsu sword moves']];
sheet.getRange('A2').format.font={name:'Arial',size:14,bold:true,color:'#253B5B'};
sheet.getRange('A2').format.rowHeight=29;
sheet.getRange('A2:L2').format.borders={bottom:{style:'thin',color:'#CED7E3'}};
const notes=[
  'Owner: Okatsu. Charged Rush and Leaping Slash are descriptive mod names, not verified official skill names.',
  'Only the two named moves have confirmed sword animations and player use. Other captured actions remain unidentified.',
  'Action IDs depend on the actor and action bank. Player C64 resolves differently from Okatsu C64.',
  'Timing IDs shown are effective lookup keys. A native timing override of -1 falls back to the motion key.',
  '30 s counts refer only to the original capture. Leaping Slash was identified later, so its capture counts are zero.',
];
sheet.getRange('A3:A7').values=notes.map(x=>[x]);
sheet.getRange('A3:L7').format.font={name:'Arial',size:10,color:'#54657C'};
function table(row,headers,data,name) {
  const last=String.fromCharCode(64+headers.length),end=row+data.length;
  sheet.getRange(`A${row}:${last}${row}`).values=[headers];
  sheet.getRange(`A${row+1}:${last}${end}`).values=data;
  const t=sheet.tables.add(`A${row}:${last}${end}`,true,name);t.showFilterButton=true;
  const h=sheet.getRange(`A${row}:${last}${row}`);
  h.format.fill='#253B5B'; h.format.font={name:'Arial',size:10,bold:true,color:'#FFFFFF'};
  h.format.horizontalAlignment='center';h.format.rowHeight=32;h.format.wrapText=true;
  h.format.borders={insideVertical:{style:'thin',color:'#FFFFFF'}};
  data.forEach((_,i)=>sheet.getRange(`A${row+1+i}:${last}${row+1+i}`).format.fill=i%2?'#F3F6FA':'#FFFFFF');
}
table(9,['Action (hex)','Action (decimal)','Move / action','Weapon identity','Motion ID','Timing ID','Player binding','Verification','30 s entries','30 s state events','Source transitions','Evidence'],rows,'OkatsuSwordCatalog');
for(const col of ['B','E','F','I','J','K']) {
  sheet.getRange(`${col}10:${col}19`).setNumberFormat('0');
  sheet.getRange(`${col}10:${col}19`).format.horizontalAlignment='right';
}
sheet.getRange('A10:A19').setNumberFormat('@');
sheet.freezePanes.freezeRows(9);
sheet.getRange('A21').values=[['Current port settings']];
sheet.getRange('A21').format.font={name:'Arial',size:10,bold:true,color:'#253B5B'};
table(22,['Action (hex)','Ki cost (base)','Startup change','Pulse starts (frame)','Recoverable cost','Fill (frames)','Hold window (frames)','Change verification'],[
  ['0C64',15,'2x speed before frame 30',65,.4,25,24,'Startup / pulse: pending'],
  ['0C66',15,'Unchanged',90,.4,25,24,'Pulse: pending'],
],'OkatsuPortSettings');
for(const col of ['B','D','F','G']) {sheet.getRange(`${col}23:${col}24`).setNumberFormat('0');sheet.getRange(`${col}23:${col}24`).format.horizontalAlignment='right';}
sheet.getRange('E23:E24').setNumberFormat('0%');sheet.getRange('E23:E24').format.horizontalAlignment='right';
sheet.getRange('A26:A38').values=[
  ['Pulse timing is in native animation frames. Cost 15 is raw move metadata; the game applies its normal modifiers.'],
  ['Player use, movement, lock-on and stance retention are user-confirmed for both named moves.'],
  ['Imported Okatsu voices are removed; weapon and movement sounds are retained (user-confirmed).'],
  ['Faster tap startup and both Ki Pulse windows are implemented. Gameplay verification is still pending.'],
  ['Resources: Okatsu must be loaded in her mission. Damage ownership is not yet independently verified.'],
  ['C65 followed C64 once in the original take; its identity is not established. Transition counts are available rows, not executed transitions.'],
  [null],
  ['Sources'],
  ['Capture: Okatsu-Capture-30s/events.jsonl and analysis.json, 24 Sep 2026. Counts are sampled observations, not animation frames.'],
  ['Profile: okatsu-prototype/session-profile.json, source action bank and loaded motion/timing resources.'],
  ['Port: okatsu-prototype/findings.json, controller-binding.json and user playtest reports, 25 Sep 2026.'],
  ['Ki Pulse: okatsu-prototype/evidence/ki-pulse-native.json. Startup: evidence/rush-windup-clock-evidence.txt.'],
  [`Nioh executable SHA256: ${findings.build_sha256}`],
];
sheet.getRange('A26:L38').format.font={name:'Arial',size:10,color:'#54657C'};
sheet.getRange('A33').format.font={name:'Arial',size:10,bold:true,color:'#253B5B'};
workbook.recalculate();
for(const original of saved) {
  const range=workbook.worksheets.getItem(original.name).getUsedRange();
  assert.deepEqual(range.values,original.values);
  assert.deepEqual(range.formulas,original.formulas);
}
assert.deepEqual(sheet.getRange('A10:L19').values,rows);
const inspected=await workbook.inspect({kind:'table',range:'Okatsu sword!A9:L11',include:'values,formulas',maxChars:3000,tableMaxRows:3,tableMaxCols:12});
const errors=await workbook.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:100},summary:'final error scan'});
await fs.writeFile(path.join(import.meta.dirname,'okatsu-verification.txt'),inspected.ndjson+'\n'+errors.ndjson);
for(const [range,name] of [['A1:L19','okatsu-catalog.png'],['A21:L38','okatsu-settings.png']]) {
  const preview=await workbook.render({sheetName:'Okatsu sword',range,scale:1,format:'png'});
  await fs.writeFile(path.join(import.meta.dirname,name),new Uint8Array(await preview.arrayBuffer()));
}
try {await fs.copyFile(file,backup,1);} catch(error) {if(error.code!=='EEXIST')throw error;}
await (await SpreadsheetFile.exportXlsx(workbook)).save(file);
await fs.rename(`${file}.inspect.ndjson`,path.join(import.meta.dirname,'okatsu-export-inspection.ndjson')).catch(error=>{if(error.code!=='ENOENT')throw error;});
console.log(JSON.stringify({file,confirmedMoves:2,unidentifiedActions:8,priorSheetsPreserved:true,errors:errors.ndjson}));
