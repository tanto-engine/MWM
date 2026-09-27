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
const pending = new Map(); let sequence = 0, capture = 0, oldCapture, delayPreview = false, cancelGroup = false;
const methods = [];
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
  pending.delete(reply.id); reply.error ? entry.reject(new Error(reply.error)) : entry.resolve(reply.result);
});
function call(method, params) {
  // Send only test-scoped production operations to Python.
  // Requests remain correlated even while status and preview reads overlap.
  // No shared settings directory is used by this worker.
  return new Promise((resolve, reject) => {
    const id = ++sequence; pending.set(id, {resolve,reject}); worker.stdin.write(JSON.stringify({id,method,params})+'\n');
  });
}
ipcMain.handle('mwm:request', async (_event, method, params={}) => {
  // Substitute chosen filenames for dialogs and deterministic events for hardware capture.
  // Deliberately deliver one cancelled binding late to exercise the generation guard.
  // All preview, remapping, import, export and Apply operations use the real worker.
  methods.push(method);
  if (method==='test_delay_preview') { delayPreview=true; return true; }
  if (method==='test_cancel_group') { cancelGroup=true; return true; }
  if (method==='preview' && delayPreview) {
    delayPreview=false; const result=await call(method,params);
    await new Promise(resolve=>setTimeout(resolve,500)); return result;
  }
  if (method==='collection') return JSON.parse(fs.readFileSync(path.join(root,'desktop-dist/collection.json'),'utf8'));
  if (method==='capture_cancel') return true;
  if (method==='capture_start') { capture++; if (capture===2 && oldCapture) setTimeout(()=>oldCapture({mask:1,label:'stale Square'}),25); return {status:'Waiting'}; }
  if (method==='capture_poll') return capture===1 ? new Promise(resolve=>{oldCapture=resolve;}) : {status:'Waiting for new input'};
  if (method==='export' || method==='import') params={...params,path:path.join(folder,'roundtrip.json')};
  if (method==='binding_import' && cancelGroup) { cancelGroup=false; return null; }
  if (method==='binding_export' || method==='binding_import') params={...params,path:path.join(folder,'group.json')};
  if (method==='enable' || method==='disable') throw new Error('Unexpected lifecycle action');
  return call(method,params);
});
app.whenReady().then(async () => {
  const window = new BrowserWindow({show:false,width:1120,height:840,webPreferences:{preload:path.join(root,'desktop/preload.cjs'),contextIsolation:true,sandbox:false,backgroundThrottling:false}});
  try {
    await window.loadFile(path.join(root,'desktop-dist/index.html'));
    const result = await window.webContents.executeJavaScript(`(async () => {
      const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
      const assert=(value,message)=>{if(!value)throw new Error(message);};
      const ready=async()=>{for(let n=0;n<100;n++){if(!document.body.inert && !document.querySelector('#apply').disabled)return;await wait(30);}throw new Error(document.querySelector('#validation').textContent);};
      const change=(input,value)=>{input.value=value;input.dispatchEvent(new Event(input.tagName==='SELECT'?'change':'input'));};
      const tab=async name=>{document.querySelector('[data-tab="'+name+'"]').click();await ready();};
      await ready(); document.querySelector('#baseline').click();await ready();
      await tab('native');
      const originalRows=document.querySelectorAll('.binding').length;
      [...document.querySelectorAll('button')].find(x=>x.textContent==='+ Add replacement').click();await ready();
      assert(document.querySelectorAll('.binding').length===originalRows+1,'Add override failed to choose a free slot');
      document.querySelector('#starter').click();await ready();await tab('moves');
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
      change(child,'3');await wait(650);assert(document.querySelector('#apply').disabled,'Stale preview enabled an invalid draft');
      change(child,'1');await ready();
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
      [...document.querySelectorAll('button')].find(x=>x.textContent==='Load group…').click();await ready();
      assert(document.querySelectorAll('main .fields select')[2].value==='jin_hayabusa.action_0c75','Group load did not restore Frost');
      await tab('speed');assert(document.querySelector('[data-speed-id="jin_hayabusa.action_0c6f"] input').value==='1','Binding module changed unrelated tuning');
      await tab('native');
      const rows=document.querySelectorAll('.binding');
      const source=rows[1].querySelectorAll('select')[0], stance=rows[1].querySelectorAll('select')[1];
      change(source,'dodge_attack');change(stance,'low');await wait(300);
      assert(document.querySelector('#apply').disabled,'Overlapping overrides were accepted');
      change(source,'heavy_attack');change(stance,'mid');await ready();
      await tab('moves');
      const devices=[...document.querySelectorAll('label')].find(x=>x.querySelector('span')?.textContent==='Controller mapping').querySelector('select');
      change(devices,'1');await ready();
      const label=text=>[...document.querySelectorAll('label')].find(x=>x.querySelector('span')?.textContent===text);
      const modifierBefore=label('Modifier').querySelector('select').value;
      const triggerBefore=label('Trigger').querySelector('select').value;
      [...document.querySelectorAll('button')].find(x=>x.textContent==='Swap buttons').click();await ready();
      assert(label('Modifier').querySelector('select').value===triggerBefore && label('Trigger').querySelector('select').value===modifierBefore,'Button swap was not atomic');
      [...document.querySelectorAll('button')].find(x=>x.textContent==='Swap buttons').click();await ready();
      label('Modifier').querySelector('button').click();await wait(80);
      label('Trigger').querySelector('button').click();await wait(180);
      assert(label('Trigger').querySelector('select').value===triggerBefore,'Cancelled capture overwrote new target');
      [...document.querySelectorAll('button')].find(x=>x.textContent==='Cancel binding').click();await ready();
      document.querySelector('#apply').click();await ready();
      document.querySelector('#reload').click();await ready();
      assert(label('Modifier').querySelector('select').value==='256','Controller remap did not persist');
      await tab('speed');
      assert(document.querySelector('[data-speed-id="jin_hayabusa.action_0c6f"] input').value==='1','Apply/reload lost tuning');
      await tab('frost');
      const frost=[...document.querySelectorAll('main .fields select')].map(x=>x.value);
      assert(frost[0]==='jin_hayabusa.action_0c71' && frost[2]==='jin_hayabusa.action_0c75','Binding edits changed Frost routes');
      await tab('moves');
      return {bindingGroups:true,freeOverrideSlots:true,speedInheritance:true,explicitNativeSpeed:true,unicodeRoundtrip:true,roundtrip:true,conflictsRejected:true,staleCaptureRejected:true,controllerRemap:true,frostPreserved:true};
    })()`);
    await window.webContents.executeJavaScript(`(async()=>{
      document.querySelector('#starter').click();
      await new Promise(resolve=>setTimeout(resolve,300));
      for(let i=0;i<50 && document.querySelector('#apply').disabled;i++) await new Promise(resolve=>setTimeout(resolve,30));
      if(!document.querySelector('#profile-name').textContent.startsWith('Sword Rebuild 1'))throw new Error('Starter did not restore its profile name');
      await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
    })()`);
    await window.webContents.capturePage().then(image=>fs.writeFileSync(path.join(folder,'bindings-1120.png'),image.toPNG()));
    window.setSize(860,640); await new Promise(resolve=>setTimeout(resolve,150));
    const fit=await window.webContents.executeJavaScript(`({width:innerWidth,overflow:document.documentElement.scrollWidth>innerWidth,mainHeight:document.querySelector('main').clientHeight,footerBottom:document.querySelector('footer').getBoundingClientRect().bottom,height:innerHeight})`);
    if(fit.overflow || fit.mainHeight<120 || fit.footerBottom>fit.height)throw new Error('Minimum window does not fit: '+JSON.stringify(fit));
    await window.webContents.capturePage().then(image=>fs.writeFileSync(path.join(folder,'bindings-860.png'),image.toPNG()));
    fs.writeFileSync(path.join(folder,'ui-result.json'),JSON.stringify({...result,fit,methods}));
    // Process exit closes the pipe after Chromium stops issuing status reads.
    app.exit(0);
  } catch(error) {
    fs.writeFileSync(path.join(folder,'ui-result.json'),JSON.stringify({error:String(error),worker:errors}));
    worker.kill();app.exit(1);
  }
});
setTimeout(()=>{worker.kill();app.exit(2);},35000).unref();
