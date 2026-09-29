// Run the actual renderer and Python configuration worker in an invisible owned window.
// Native dialogs and physical binding are replaced at the IPC boundary; no game is opened.
// This file is called by Engine's maintained offline suite through the MWM product cases.
const { app, BrowserWindow, ipcMain } = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { createInterface } = require('node:readline');
const root = path.resolve(__dirname, '..');
const folder = process.argv[2], python = process.argv[3];
app.setPath('userData', path.join(folder, 'electron-state'));
const pending = new Map(); let sequence = 0, capture = 0, oldCapture, lateRouteCapture, delayPreview = false, cancelGroup = false;
let delaySnapshot = false, waitSnapshot, snapshotStarted, releaseSnapshot;
const methods = [];
let phase = 'startup';
let simulatedRunning = false, failExport = false, failController = false, savedGroup;
const worker = spawn(python, ['-B', path.join(__dirname, 'desktop_worker_fixture.py'), folder], { windowsHide: true, stdio: ['pipe','pipe','pipe'] });
process.on('uncaughtException', error => {
  // A test failure must never open Electron's blocking error dialog.
  // Preserve the actual exception beside the temporary screenshots.
  // Stop only this fixture's worker and window process.
  fs.writeFileSync(path.join(folder,'ui-result.json'),JSON.stringify({error:String(error)}));
  worker.kill();app.exit(1);
});
let errors = ''; worker.stderr.on('data', value => { errors += value; });
createInterface({ input: worker.stdout }).on('line', line => {
  // Match each reply to the renderer request that initiated it.
  // Invalid production replies fail visibly instead of bypassing worker validation.
  // The test host uses the same JSON line protocol as the real application.
  const reply = JSON.parse(line), entry = pending.get(reply.id);
  pending.delete(reply.id); reply.error ? entry.reject(Object.assign(new Error(reply.error.message), {kind:reply.error.kind})) : entry.resolve(reply.result);
});
function call(method, params) {
  // Send only test-scoped production operations to Python.
  // Requests remain correlated even while status and preview reads overlap.
  // No shared settings directory is used by this worker.
  return new Promise((resolve, reject) => {
    const id = ++sequence; pending.set(id, {resolve,reject}); worker.stdin.write(JSON.stringify({id,method,params})+'\n');
  });
}
async function request(_event, method, params={}) {
  // Substitute chosen filenames for dialogs and deterministic events for hardware capture.
  // Deliberately deliver one cancelled binding late to exercise the generation guard.
  // All preview, remapping, import, export and Apply operations use the real worker.
  methods.push(method);
  if (method==='test_runtime_running') { simulatedRunning=params; return true; }
  if (method==='test_fail_controller') { failController=true; return true; }
  if (method==='test_delay_snapshot') { delaySnapshot=true; waitSnapshot=new Promise(resolve=>{snapshotStarted=resolve;}); return true; }
  if (method==='test_wait_snapshot') return waitSnapshot;
  if (method==='test_release_snapshot') { releaseSnapshot(); return true; }
  if (method==='test_export_error') { failExport=true; return true; }
  if (method==='test_invalid_group') {
    const file=path.join(folder,'group.json');
    if (params) { savedGroup=fs.readFileSync(file,'utf8'); const value=JSON.parse(savedGroup); value.bindings.frost_moon.high=value.bindings.frost_moon.low; fs.writeFileSync(file,JSON.stringify(value)); }
    else fs.writeFileSync(file,savedGroup);
    return true;
  }
  if (method==='export' && failExport) { failExport=false; throw new Error('Fixture: file is read-only'); }
  if (method==='snapshot') {
    const result={...await call(method,params),running:simulatedRunning};
    if (delaySnapshot) { delaySnapshot=false; await new Promise(resolve=>{releaseSnapshot=resolve; snapshotStarted();}); }
    return result;
  }
  if (method==='controller' && failController) { failController=false; throw new Error('Fixture: controller unavailable'); }
  if (method==='test_delay_preview') { delayPreview=true; return true; }
  if (method==='test_cancel_group') { cancelGroup=true; return true; }
  if (method==='test_release_route_capture') { lateRouteCapture({mask:0x40000000,label:'stale route press'}); return true; }
  if (method==='preview' && delayPreview) {
    delayPreview=false; const result=await call(method,params);
    await new Promise(resolve=>setTimeout(resolve,500)); return result;
  }
  if (method==='collection') return JSON.parse(fs.readFileSync(path.join(root,'desktop-dist/collection.json'),'utf8'));
  if (method==='capture_cancel') return true;
  if (method==='capture_start') { capture++; if (capture===2 && oldCapture) setTimeout(()=>oldCapture({mask:1,label:'stale Square'}),25); return {status:'Waiting'}; }
  if (method==='capture_poll') return capture===1 ? new Promise(resolve=>{oldCapture=resolve;}) : capture===3 || capture===4
    ? {mask:capture===3 ? 0x2000 : 0x8000,label:capture===3 ? 'Circle / B' : 'Triangle / Y',calibration:{schema:1,device:{backend:'xinput',slot:1},lb_mask:0x100,lt:{axis:'lt',neutral:0,full:255},controller_slot:1}}
    : capture===5 ? new Promise(resolve=>{lateRouteCapture=resolve;})
    : {status:'Waiting for new input'};
  if (method==='haptic') return false;
  if (method==='export' || method==='import') params={...params,path:path.join(folder,'roundtrip.json')};
  if (method==='binding_import' && cancelGroup) { cancelGroup=false; return null; }
  if (method==='binding_export' || method==='binding_import') params={...params,path:path.join(folder,'group.json')};
  if (method==='enable' || method==='disable') throw new Error('Unexpected lifecycle action');
  return call(method,params);
}
ipcMain.handle('mwm:request', async (...args) => {
  try { return {ok:true,result:await request(...args)}; }
  catch (error) { return {ok:false,error:{kind:error.kind||'operation',message:error.message}}; }
});
app.whenReady().then(async () => {
  const window = new BrowserWindow({show:false,width:1120,height:800,webPreferences:{preload:path.join(root,'desktop/preload.cjs'),contextIsolation:true,sandbox:false,backgroundThrottling:false}});
  try {
    const ui = path.join(folder,'ui'); fs.mkdirSync(ui);
    for (const name of ['index.html','style.css']) fs.copyFileSync(path.join(root,'desktop',name),path.join(ui,name));
    fs.writeFileSync(path.join(ui,'renderer.js'),require('esbuild').transformSync(fs.readFileSync(path.join(root,'desktop/renderer.ts'),'utf8'),{loader:'ts',format:'iife'}).code);
    await window.loadFile(path.join(ui,'index.html'));
    const result = await window.webContents.executeJavaScript(`(async () => {
      const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
      const assert=(value,message)=>{if(!value)throw new Error(message);};
      const ready=async()=>{for(let n=0;n<100;n++){if(!document.body.inert && document.querySelector('#validation').dataset.state==='valid')return;await wait(30);}throw new Error(document.querySelector('#validation').textContent);};
      const change=(input,value)=>{input.value=value;input.dispatchEvent(new Event(input.tagName==='SELECT'?'change':'input'));};
      const tab=async name=>{document.querySelector('[data-tab="'+name+'"]').click();await ready();};
      const dismiss=()=>document.querySelector('#binding-error button').click();
      await ready();
      assert(document.querySelectorAll('.stance-card').length===3,'Default view is not grouped by stance');
      assert(document.querySelector('#disable').hidden && !document.querySelector('#enable').hidden,'Disabled runtime shows both actions');
      assert(document.querySelector('#apply').disabled,'Saved moveset still offers redundant save');
      await tab('controls');
      const failedDevice=[...document.querySelectorAll('label')].find(x=>x.querySelector('span')?.textContent==='Controller mapping').querySelector('select');
      await window.mwm.request('test_fail_controller');change(failedDevice,'1');await wait(350);
      assert(document.querySelector('#binding-error').open,'Failed controller translation was not reported');
      assert(failedDevice.value==='saved' && document.querySelector('#apply').disabled && !document.querySelector('#profile-name').textContent.includes('unsaved'),'Failed controller translation changed clean editor state');
      dismiss();await tab('overview');
      await window.mwm.request('test_delay_snapshot');await window.mwm.request('test_wait_snapshot');
      await window.mwm.request('test_runtime_running',true);
      document.querySelector('#reload').click();await ready();
      assert(!document.querySelector('#disable').hidden,'Reload did not show newer running status');
      await window.mwm.request('test_release_snapshot');await wait(250);
      assert(!document.querySelector('#disable').hidden,'Old status poll overwrote newer runtime state');
      await window.mwm.request('test_runtime_running',false);
      document.querySelector('#reload').click();await ready();
      // An independent tool can save while this window is open; use only fixture settings.
      // Clean views should follow that saved model, while real draft edits and focus survive polling.
      // Both saves execute production Python Apply rather than replacing renderer state directly.
      const external=await window.mwm.request('snapshot');
      external.preset={...external.preset,name:'External saved moveset',low_heavy:null,skill_bindings:external.preset.skill_bindings.filter(row=>row.source!=='dodge_attack'||row.stance!=='low')};
      await window.mwm.request('apply',external);
      await wait(2300);await ready();
      assert(document.querySelector('#profile-name').textContent==='External saved moveset','External saved preset did not reach the clean UI');
      assert(document.querySelector('[data-assignment="low-heavy"]').value==='','External saved assignment stayed stale');
      await tab('controls');
      const externalName=[...document.querySelectorAll('label')].find(x=>x.querySelector('span')?.textContent==='Moveset name').querySelector('input');
      externalName.focus();await wait(2000);
      assert(document.activeElement===externalName && externalName.isConnected,'Routine polling reset clean field focus');
      change(externalName,'Pending local name');await ready();
      external.preset={...external.preset,name:'Second external moveset',hold_seconds:.4};
      await window.mwm.request('apply',external);await window.mwm.request('test_runtime_running',true);await wait(2300);
      assert(externalName.value==='Pending local name' && externalName.isConnected && document.activeElement===externalName,'External save overwrote or rebuilt a dirty editor');
      assert(document.querySelector('#profile-name').textContent.startsWith('Pending local name'),'External snapshot replaced the draft header');
      assert(document.querySelector('#apply').disabled && document.querySelector('#validation').textContent.includes('Disable the mod before saving changes'),'Running mod still permits a saved graph change');
      await window.mwm.request('test_runtime_running',false);
      document.querySelector('#reload').click();await ready();
      assert(document.querySelector('#profile-name').textContent==='Second external moveset','Discard did not load latest saved model');
      await tab('overview');
      document.querySelector('#trial').click();await ready();
      assert(document.querySelector('#enable').disabled,'Enable bypasses unsaved draft');
      assert(document.querySelectorAll('.stance-card [data-assignment^="hold:"]').length===3,'Hold Triangle is not directly selectable in every stance');
      assert(![...document.querySelectorAll('main option')].some(x=>/\\b(?:0x)?[0-9A-F]{4}\\b/.test(x.textContent)),'Overview exposes source hex IDs');
      const lowHold=document.querySelector('[data-assignment="hold:low"]');
      assert([...lowHold.options].some(option=>option.value==='okatsu.charged_rush'),'Charged Rush is absent from held-heavy choices');
      const highHold=document.querySelector('[data-assignment="hold:high"]');
      assert(lowHold.getAttribute('aria-label')==='Hold Triangle / Y','Held input does not identify the controller button');
      assert([...lowHold.options].some(x=>x.value==='jin_hayabusa.action_0c79' && x.text.includes('Launcher only')),'Standalone launcher is unclear');
      assert([...lowHold.options].some(x=>x.value==='jin_hayabusa.izuna_drop' && x.text.includes('Launcher + Izuna Drop')),'Complete Izuna is unclear');
      change(lowHold,'jin_hayabusa.action_0c79');await ready();
      change(highHold,'jin_hayabusa.action_0c79');await wait(300);
      assert(document.querySelector('#binding-error')?.open,'Invalid duplicate hold has no in-app explanation popup');
      assert(document.querySelector('#error-reason').textContent.startsWith('This bind is incompatible because: '),'Incompatible popup lost its required explanation');
      assert(document.querySelector('#error-reason').textContent.includes(highHold.selectedOptions[0].textContent),'Error reason disagrees with the selected move name');
      assert(!document.querySelector('#error-reason').textContent.includes('Error invoking remote method'),'Popup leaks the Electron transport wrapper');
      assert(document.querySelector('#apply').disabled && document.querySelector('#enable').disabled,'Invalid duplicate hold remains saveable');
      assert(highHold.value==='jin_hayabusa.action_0c79','Invalid edit was silently discarded');
      assert(document.querySelector('[data-assignment="chord:tap"]').selectedOptions[0].textContent==='bloodborne gun shot','Gun move does not use its canonical name');
      assert(document.activeElement===document.querySelector('#binding-error button'),'Popup has no keyboard focus');
      dismiss();await wait(2000);
      assert(!document.querySelector('#binding-error').open,'Status polling repeated the incompatible popup');
      change(highHold,'jin_hayabusa.izuna_drop');await ready();
      change(highHold,'');await ready();
      assert(highHold.isConnected && highHold.value==='','Cleared held assignment cannot be reassigned');
      const chordHold=document.querySelector('[data-assignment="chord:hold"]');
      change(chordHold,'jin_hayabusa.izuna_drop');await wait(300);
      assert(document.querySelector('#apply').disabled && document.querySelector('#validation').textContent.includes('different stances'),'Same-stance Izuna conflict is not explained');
      dismiss();
      change(chordHold,'');await ready();
      change(highHold,'jin_hayabusa.izuna_drop');await ready();
      await tab('controls');
      const chordStance=[...document.querySelectorAll('label')].find(x=>x.querySelector('span')?.textContent==='Custom input stance').querySelector('select');
      change(chordStance,'any');await wait(300);
      assert(document.querySelector('#apply').disabled && document.querySelector('#validation').textContent.includes('Choose Low, Mid or High'),'Graph chord stance requirement is not explained');
      dismiss();
      change(chordStance,'low');await ready();await tab('overview');
      const lowQuick=document.querySelector('[data-assignment="native:low:light_attack"]');
      assert(lowQuick && lowQuick.value==='toyotomi_hideyori.action_0d30','Trial route is missing');
      change(lowQuick,'');await ready();
      const frostHigh=document.querySelector('[data-assignment="frost:high"]');
      change(frostHigh,'jin_hayabusa.action_0c71');await wait(300);
      assert(document.querySelector('#apply').disabled,'Overview ignored a conflicting route');
      dismiss();
      change(frostHigh,'okatsu.leaping_slash');await ready();
      document.querySelector('#apply').click();await ready();
      const savedOverview=await window.mwm.request('snapshot');
      assert(!savedOverview.preset.skill_bindings.some(x=>x.source==='light_attack'),'Overview disable was not persisted');
      assert(savedOverview.preset.frost_moon.high==='okatsu.leaping_slash','Overview move edit did not reach Python');
      assert(savedOverview.preset.stance_holds.low==='jin_hayabusa.action_0c79' && savedOverview.preset.stance_holds.high==='jin_hayabusa.izuna_drop','Separate launcher and Izuna stances did not persist');
      assert(!document.querySelector('#notice').textContent,'Saved settings left stale success text');
      await tab('controls');
      const pulseTrigger=[...document.querySelectorAll('label')].find(x=>x.querySelector('span')?.textContent==='Trigger').querySelector('select');
      const previousTrigger=pulseTrigger.value;
      change(pulseTrigger,[...pulseTrigger.options].find(x=>x.textContent==='R1 / RB').value);await wait(300);
      assert(document.querySelector('#apply').disabled && document.querySelector('#validation').textContent.includes('Ki Pulse'),'Reserved Frost input was not rejected before Save');
      dismiss();
      change(pulseTrigger,previousTrigger);await ready();
      document.querySelector('#baseline').click();await ready();
      await tab('native');
      assert([...document.querySelectorAll('.binding')].every(row=>[...row.querySelectorAll('label')].some(label=>label.querySelector('span')?.textContent==='Activation')),'Existing route has no per-row activation selector');
      const originalRows=document.querySelectorAll('.binding').length;
      [...document.querySelectorAll('button')].find(x=>x.textContent==='+ Add original route').click();await ready();
      assert(document.querySelectorAll('.binding').length===originalRows+1,'Add override failed to choose a free slot');
      const newOriginal=[...document.querySelectorAll('.binding')].at(-1);
      const activation=[...newOriginal.querySelectorAll('label')].find(x=>x.querySelector('span')?.textContent==='Activation').querySelector('select');
      change(activation,'custom');await ready();
      const converted=[...document.querySelectorAll('.binding')].at(-1);
      assert(converted.querySelector('.control-note').textContent.includes('stay unchanged'),'Custom mode does not explain original input');
      assert(![...converted.querySelectorAll('label')].some(x=>x.querySelector('span')?.textContent==='Source'),'Custom route exposes an inert source selector');
      assert([...converted.querySelectorAll('label')].some(x=>x.querySelector('span')?.textContent==='Modifier' && x.querySelector('button')?.textContent==='Press to bind'),'Custom route has no button capture');
      assert([...converted.querySelectorAll('label')].some(x=>x.querySelector('span')?.textContent==='Gesture'),'Custom route has no tap/hold choice');
      [...document.querySelectorAll('button')].find(x=>x.textContent==='+ Add custom input').click();await ready();
      assert(document.querySelectorAll('.binding').length===originalRows+2,'Custom add did not permit another route');
      assert(document.querySelector('.slot-count').textContent.includes('custom routes'),'Separate custom capacity is missing');
      document.querySelector('#apply').click();await ready();
      const savedRoutes=(await window.mwm.request('snapshot')).preset.skill_bindings;
      assert(savedRoutes.filter(row=>row.input).length===2,'Custom routes did not persist');
      await tab('overview');
      assert(document.querySelector('.overview-heading').textContent.includes('2 custom button routes'),'Sword overview hides custom routes');
      const customKeys=[...document.querySelectorAll('[data-assignment^="custom:"]')].map(x=>x.dataset.assignment);
      assert(customKeys.length===2 && new Set(customKeys).size===2,'Custom overview routes share an assignment key');
      document.querySelector('#starter').click();await ready();await tab('controls');
      const profileName='Sword – テスト';
      const profile=[...document.querySelectorAll('label')].find(x=>x.querySelector('span')?.textContent==='Moveset name').querySelector('input');
      change(profile,profileName);await ready();
      await tab('speed');
      const root=document.querySelector('[data-speed-id="jin_hayabusa.action_0c6e"] input');
      const child=document.querySelector('[data-speed-id="jin_hayabusa.action_0c6f"] input');
      change(root,'0.5');await ready();
      assert(child.closest('[data-speed-id]').querySelector('output').textContent.includes('0.5×'),'Inherited preview is wrong');
      change(child,'1');await ready();
      assert(child.closest('[data-speed-id]').querySelector('output').textContent.includes('1×'),'Explicit native speed was lost');
      await window.mwm.request('test_delay_preview');change(child,'1.1');await wait(240);
      change(child,'3');await wait(650);assert(document.querySelector('#apply').disabled,'Stale preview enabled an invalid draft');dismiss();
      change(child,'1');await ready();
      await window.mwm.request('test_export_error');document.querySelector('#save').click();await wait(100);
      assert(document.querySelector('#binding-error').open && document.querySelector('#error-reason').textContent==='Fixture: file is read-only','File error was mislabeled as an incompatible bind');
      dismiss();
      document.querySelector('#save').click();await ready();
      change(child,'0.75');await ready();document.querySelector('#load').click();await ready();
      assert(document.querySelector('[data-speed-id="jin_hayabusa.action_0c6f"] input').value==='1','Export/import lost explicit speed');
      assert(document.querySelector('#profile-name').textContent.startsWith(profileName),'Unicode profile name changed during worker roundtrip');
      await tab('frost');document.querySelector('.binding-modules').open=true;
      change(document.querySelector('[aria-label="Binding group"]'),'frost');
      document.querySelector('[data-binding-export]').click();await ready();
      const high=document.querySelectorAll('main .fields select')[2];change(high,'');await ready();
      await window.mwm.request('test_cancel_group');
      [...document.querySelectorAll('button')].find(x=>x.textContent==='Load group…').click();await ready();
      assert(high.value==='','Cancelled group load changed the draft');
      await window.mwm.request('test_invalid_group',true);
      [...document.querySelectorAll('button')].find(x=>x.textContent==='Load group…').click();await wait(300);
      assert(document.querySelector('#binding-error').open && document.querySelector('#error-reason').textContent.startsWith('This bind is incompatible because: '),'Group action did not explain its actual validation failure');
      assert(high.value==='','Failed group import changed the draft');
      dismiss();await ready();
      assert(!document.querySelector('#apply').disabled && !document.querySelector('#binding-error').open,'Retained valid draft did not recover after failed group import');
      await window.mwm.request('test_invalid_group',false);
      [...document.querySelectorAll('button')].find(x=>x.textContent==='Load group…').click();await ready();
      assert(document.querySelectorAll('main .fields select')[2].value==='jin_hayabusa.action_0c75','Group load did not restore Frost');
      await tab('speed');assert(document.querySelector('[data-speed-id="jin_hayabusa.action_0c6f"] input').value==='1','Binding module changed unrelated tuning');
      await tab('native');
      const rows=document.querySelectorAll('.binding');
      const source=rows[1].querySelectorAll('select')[0], stance=rows[1].querySelectorAll('select')[1];
      change(source,'dodge_attack');change(stance,'low');await wait(300);
      assert(document.querySelector('#apply').disabled,'Overlapping overrides were accepted');
      dismiss();
      change(source,'heavy_attack');change(stance,'mid');await ready();
      await tab('controls');
      const devices=[...document.querySelectorAll('label')].find(x=>x.querySelector('span')?.textContent==='Controller mapping').querySelector('select');
      change(devices,'1');await ready();
      const label=text=>[...document.querySelectorAll('label')].find(x=>x.querySelector('span')?.textContent===text);
      const modifierBefore=label('Modifier').querySelector('select').value;
      const triggerBefore=label('Trigger').querySelector('select').value;
      [...document.querySelectorAll('button')].find(x=>x.textContent==='Swap buttons').click();await ready();
      assert(label('Modifier').querySelector('select').value===triggerBefore && label('Trigger').querySelector('select').value===modifierBefore,'Button swap was not atomic');
      [...document.querySelectorAll('button')].find(x=>x.textContent==='Swap buttons').click();await ready();
      label('Modifier').querySelector('button').click();await wait(80);
      assert(!document.querySelector('#capture-status').hidden && document.querySelector('#capture-status').textContent==='Waiting', 'Controller capture status is hidden');
      label('Trigger').querySelector('button').click();await wait(180);
      assert(label('Trigger').querySelector('select').value===triggerBefore,'Cancelled capture overwrote new target');
      [...document.querySelectorAll('button')].find(x=>x.textContent==='Cancel binding').click();await ready();
      document.querySelector('#apply').click();await ready();
      document.querySelector('#reload').click();await ready();
      assert(label('Modifier').querySelector('select').value==='256','Controller remap did not persist');
      label('Modifier').querySelector('button').click();
      for(let i=0;i<100 && label('Modifier').querySelector('select').value!=='8192';i++)await wait(30);
      await ready();
      assert(label('Modifier').querySelector('select').value==='8192','Physical capture did not set the pressed button');
      assert(document.querySelector('#capture-status').hidden,'Capture status remained visible after binding');
      assert(label('Controller mapping').querySelector('select').value==='2','Physical capture did not select its XInput slot');
      document.querySelector('#apply').click();await ready();
      const captured=await window.mwm.request('snapshot');
      assert(captured.preset.modifier_mask===0x2000 && captured.calibration.controller_slot===1,'Physical capture did not persist controller and button together');
      await tab('speed');
      assert(document.querySelector('[data-speed-id="jin_hayabusa.action_0c6f"] input').value==='1','Apply/reload lost tuning');
      await tab('frost');
      const frost=[...document.querySelectorAll('main .fields select')].map(x=>x.value);
      assert(frost[0]==='jin_hayabusa.action_0c71' && frost[2]==='jin_hayabusa.action_0c75','Binding edits changed Frost routes');
      await tab('native');
      [...document.querySelectorAll('button')].find(x=>x.textContent==='+ Add custom input').click();await ready();
      const routeField=text=>[...[...document.querySelectorAll('.binding')].at(-1).querySelectorAll('label')].find(x=>x.querySelector('span')?.textContent===text);
      assert(/route \\d+/.test(routeField('Trigger').querySelector('button').getAttribute('aria-label')),'Route capture lacks an accessible target');
      assert([...routeField('Modifier').querySelector('select').options].every(x=>x.value==='256'),'Unsupported custom modifier was offered');
      assert([...routeField('Trigger').querySelector('select').options].length===4,'Unsupported custom triggers were offered');
      routeField('Trigger').querySelector('button').click();
      for(let i=0;i<100 && routeField('Trigger').querySelector('select').value!=='32768';i++)await wait(30);
      await ready();
      assert(routeField('Trigger').querySelector('select').value==='32768','Per-route physical capture missed its target');
      assert(routeField('Modifier').querySelector('select').value==='256','Per-route capture changed the other button');
      change(routeField('Gesture').querySelector('select'),'hold');await ready();
      document.querySelector('#apply').click();await ready();
      const savedCustom=(await window.mwm.request('snapshot')).preset.skill_bindings.at(-1);
      assert(savedCustom.input.trigger_mask===32768 && savedCustom.input.modifier_mask===256 && savedCustom.input.gesture==='hold','Captured custom chord did not persist');
      routeField('Trigger').querySelector('button').click();await wait(80);
      assert(document.querySelector('#capture-status')?.textContent.includes('Route') && document.querySelector('#capture-status')?.textContent.includes('Waiting'),'Route capture did not identify its active row');
      [...[...document.querySelectorAll('.binding')].at(-1).querySelectorAll(':scope > button')].find(x=>x.textContent==='Remove').click();await ready();
      [...document.querySelectorAll('button')].find(x=>x.textContent==='+ Add custom input').click();await ready();
      const replacementTrigger=routeField('Trigger').querySelector('select').value;
      await window.mwm.request('test_release_route_capture');await wait(150);
      assert(routeField('Trigger').querySelector('select').value===replacementTrigger && document.querySelector('#validation').dataset.state==='valid','Late route capture changed a replacement row');
      await tab('controls');
      return {externalSaveSynced:true,dirtyDraftProtected:true,pollingFocusPreserved:true,overviewEditsPersisted:true,singleSaveAction:true,runtimeSeparated:true,humanMoveNames:true,bindingGroups:true,freeOverrideSlots:true,customRoutes:true,customCapture:true,speedInheritance:true,explicitNativeSpeed:true,unicodeRoundtrip:true,roundtrip:true,conflictsRejected:true,staleCaptureRejected:true,controllerRemap:true,frostPreserved:true};
    })()`);
    if (process.env.MWM_UI_SHOT) {
      await window.webContents.executeJavaScript(`(async()=>{
        const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
        document.querySelector('[data-tab="native"]').click();
        for(let i=0;i<100 && (document.body.inert || document.querySelector('#validation').dataset.state!=='valid');i++)await wait(30);
        [...document.querySelectorAll('button')].find(x=>x.textContent==='+ Add custom input').click();
        for(let i=0;i<100 && (document.body.inert || document.querySelector('#validation').dataset.state!=='valid');i++)await wait(30);
        if(document.querySelectorAll('.binding.custom-route').length<2)throw new Error('Screenshot setup lacks two custom routes');
        const search=document.querySelector('[aria-label="Filter input routes"]');search.value='tap';search.dispatchEvent(new Event('input'));
      })()`);
      window.showInactive(); window.setSize(1104,1200); await new Promise(resolve=>setTimeout(resolve,250));
      fs.writeFileSync(process.env.MWM_UI_SHOT,(await window.webContents.capturePage()).toPNG());
    }
    await window.webContents.executeJavaScript(`(async()=>{
      document.querySelector('[data-tab="native"]').click();
      for(let i=0;i<100 && (document.body.inert || document.querySelector('#validation').dataset.state!=='valid');i++)await new Promise(resolve=>setTimeout(resolve,30));
    })()`);
    window.setSize(700,800);await new Promise(resolve=>setTimeout(resolve,150));
    const narrow=await window.webContents.executeJavaScript(`({overflow:document.documentElement.scrollWidth>innerWidth,fields:[...document.querySelectorAll('.binding .field')].every(x=>x.getBoundingClientRect().right<=innerWidth)})`);
    if(narrow.overflow || !narrow.fields)throw new Error('Narrow custom routes overflow: '+JSON.stringify(narrow));
    await window.webContents.executeJavaScript(`(async()=>{
      document.querySelector('[data-tab="overview"]').click();
      await new Promise(resolve=>setTimeout(resolve,250));
      document.querySelector('#trial').click();
      await new Promise(resolve=>setTimeout(resolve,300));
      for(let i=0;i<50 && document.querySelector('#validation').dataset.state!=='valid';i++) await new Promise(resolve=>setTimeout(resolve,30));
      if(!document.querySelector('#profile-name').textContent.startsWith('Sword Rebuild 1'))throw new Error('Trial did not restore its profile name');
      await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
    })()`);
    phase = 'layout'; window.showInactive();
    window.setSize(860,640); await new Promise(resolve=>setTimeout(resolve,150));
    const fit=await window.webContents.executeJavaScript(`({width:innerWidth,overflow:document.documentElement.scrollWidth>innerWidth,mainHeight:document.querySelector('main').clientHeight,mainOverflow:document.querySelector('main').scrollHeight>document.querySelector('main').clientHeight,footerBottom:document.querySelector('footer').getBoundingClientRect().bottom,height:innerHeight,labelSize:parseFloat(getComputedStyle(document.querySelector('.assignment>span')).fontSize),valueSize:parseFloat(getComputedStyle(document.querySelector('.assignment select')).fontSize)})`);
    if(fit.labelSize<12 || fit.valueSize<13 || fit.overflow || fit.mainHeight<300 || fit.footerBottom>fit.height)throw new Error('Minimum window does not fit: '+JSON.stringify(fit));
    // Retain a terminal failure through the real Python snapshot, without starting Engine.
    // Saving a preset must not replace this independent runtime diagnosis with success copy.
    fs.writeFileSync(path.join(folder,'play-status.json'),JSON.stringify({state:'preparation_failed',detail:'Fixture: resource preparation failed. The mod is off.'}));
    await window.webContents.executeJavaScript(`(async()=>{
      for(let i=0;i<80;i++){
        if(document.querySelector('#runtime-detail').textContent.includes('Fixture:'))break;
        await new Promise(resolve=>setTimeout(resolve,50));
      }
      if(!document.querySelector('#runtime-detail').textContent.includes('Fixture:'))throw new Error('Terminal failure was lost after Engine exited');
      if(!document.querySelector('#disable').hidden || document.querySelector('#enable').hidden)throw new Error('Runtime buttons contradict stopped Engine');
      if(document.querySelector('#notice').textContent)throw new Error('Stale action success hides runtime failure');
    })()`);
    if(methods.some(method=>method==='enable'||method==='disable'))throw new Error('UI fixture attempted gameplay lifecycle');
    fs.writeFileSync(path.join(folder,'ui-result.json'),JSON.stringify({...result,terminalFailureVisible:true,noLifecycleCalls:true,fit,methods}));
    // Process exit closes the pipe after Chromium stops issuing status reads.
    app.exit(0);
  } catch(error) {
    fs.writeFileSync(path.join(folder,'ui-result.json'),JSON.stringify({error:String(error),worker:errors}));
    worker.kill();app.exit(1);
  }
});
setTimeout(()=>{fs.writeFileSync(path.join(folder,'ui-result.json'),JSON.stringify({timeout:true,phase,lastMethods:methods.slice(-20),worker:errors}));worker.kill();app.exit(2);},60000).unref();
