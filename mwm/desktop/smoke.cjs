const fs = require('node:fs');
const path = require('node:path');

async function runSmoke(window, call, report) {
  // Exercise the actual packaged renderer and worker without enabling any game feature.
  // A copied EXE must supply its own Python, preset data and research collection.
  // Saved settings and the report stay beside the explicitly supplied smoke output path.
  const screen = await window.webContents.executeJavaScript(`(async () => {
    const wait = () => new Promise(resolve => setTimeout(resolve, 50));
    for (let i=0;i<200;i++) {
      if (!document.body.inert && document.querySelector('#validation').dataset.state==='valid') break;
      await wait();
    }
    if (document.querySelector('#validation').dataset.state!=='valid') throw new Error(document.querySelector('#notice').textContent);
    const collection=await window.mwm.request('collection');
    if (!collection.moves.length) throw new Error('Packaged move collection missing');
    if (!collection.unreviewed || collection.unreviewed.signatures.length !== collection.unreviewed.distinct_signatures) throw new Error('Packaged recording index missing');
    return {datasetMoves:collection.moves.length,unreviewedActions:collection.unreviewed.distinct_signatures};
  })()`);
  // Capture the actual first-open app before test edits; the release keeps this image with its receipt.
  await window.webContents.executeJavaScript('document.fonts.ready.then(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))');
  fs.writeFileSync(path.join(path.dirname(report), 'ui-preview.png'), (await window.webContents.capturePage()).toPNG());
  const uiRebinding = await window.webContents.executeJavaScript(`(async () => {
    // Change the same visible controls used by players and save through the normal renderer.
    // Separate stances keep the standalone launcher and paired Izuna graphs distinct.
    // Read the saved worker state, so merely changing a dropdown cannot pass this check.
    const wait = () => new Promise(resolve => setTimeout(resolve, 50));
    async function ready() {
      for (let i=0;i<200;i++) {
        if (!document.body.inert && document.querySelector('#validation').dataset.state==='valid') return;
        await wait();
      }
      throw new Error('Packaged rebinding did not validate: '+document.querySelector('#validation').textContent);
    }
    for (const [stance, move] of [['low','jin_hayabusa.action_0c79'],['high','jin_hayabusa.izuna_drop']]) {
      [...document.querySelectorAll('.skill-stance')].find(button=>button.textContent===stance.toUpperCase()).click();await ready();
      if (document.querySelector('.skill-stance[aria-selected="true"]')?.textContent!==stance.toUpperCase()) throw new Error('Stance tab did not select '+stance);
      const select=document.querySelector('[data-assignment="hold:'+stance+'"]');
      if (!select?.closest('.skill-row') || ![...select.options].some(option=>option.value===move)) throw new Error('Missing held Triangle choice: '+move);
      select.value=move;select.dispatchEvent(new Event('change',{bubbles:true}));await wait();await ready();
      if (stance==='low') {
        // Reproduce the player's duplicate High launcher, through the packaged renderer and IPC.
        // Reject it visibly without persisting either pending hold, then correct the draft normally.
        [...document.querySelectorAll('.skill-stance')].find(button=>button.textContent==='HIGH').click();await ready();
        const high=document.querySelector('[data-assignment="hold:high"]');
        high.value=move;high.dispatchEvent(new Event('change',{bubbles:true}));
        for (let i=0;i<200 && !document.querySelector('#binding-error').open;i++) await wait();
        const reason=document.querySelector('#error-reason').textContent;
        if (!document.querySelector('#binding-error').open || !reason.startsWith('This bind is incompatible because:')
            || !reason.includes('Low hold Triangle / Y') || !reason.includes('High hold Triangle / Y')
            || !document.querySelector('#apply').disabled || !document.querySelector('#enable').disabled)
          throw new Error('Packaged incompatible binding was not explained: '+reason);
        const unchanged=await window.mwm.request('snapshot');
        if (unchanged.preset.stance_holds.low || unchanged.preset.stance_holds.high) throw new Error('Invalid edit changed saved bindings');
        document.querySelector('#binding-error button').click();
        high.value='';high.dispatchEvent(new Event('change',{bubbles:true}));await ready();
      }
    }
    document.querySelector('#apply').click();await wait();await ready();
    const saved=await window.mwm.request('snapshot');
    if (saved.preset.stance_holds.low!=='jin_hayabusa.action_0c79' || saved.preset.stance_holds.high!=='jin_hayabusa.izuna_drop') throw new Error('Packaged UI did not save held bindings');
    return true;
  })()`);
  const snapshot = await call('snapshot');
  const preset = snapshot.preset;
  preset.name = 'Packaged check – テスト';
  const params = {...snapshot, preset, nioh_exe:'C:\\Game path test\\nioh.exe'};
  params.preset = await call('add_override', {...params, mode:'custom'});
  params.preset = await call('add_override', {...params, mode:'custom'});
  const custom = params.preset.skill_bindings.filter(row => row.input);
  if (custom.length !== 2) throw new Error('Packaged worker did not add independent custom routes');
  custom[1].input.trigger_mask = 8; // DS4 Triangle / XInput Y, distinct from the first Circle/B route.
  const compiled = await call('preview', params);
  const saved = await call('apply', params);
  if (saved.preset.name !== preset.name || saved.nioh_exe !== params.nioh_exe) throw new Error('Packaged settings roundtrip failed');
  const file = path.join(path.dirname(report), 'smoke-bindings.json');
  await call('binding_export', {...params,group:'frost',path:file});
  const loaded = await call('binding_import', {...params,group:'frost',path:file});
  if (JSON.stringify(loaded.frost_moon) !== JSON.stringify(preset.frost_moon)) throw new Error('Packaged bindings roundtrip failed');
  // Translate the saved logical buttons into Xbox/XInput, then rebind the custom chord to LB+B.
  // Preview and persistence use the bundled Engine, with launcher and Frost bindings preserved.
  const xbox = await call('controller', {...params,choice:'1'});
  const mapped = xbox.preset.skill_bindings.filter(row => row.input).map(row => [row.input.modifier_mask,row.input.trigger_mask]);
  if (JSON.stringify(mapped) !== JSON.stringify([[0x100,0x2000],[0x100,0x8000]])) throw new Error('Custom route buttons did not follow the controller mapping');
  xbox.preset.modifier_mask=0x100;xbox.preset.trigger_mask=0x2000;
  xbox.preset.chord_stance='high'; // Keep the global LB+B tap separate from custom Low/Mid routes.
  const rebound={...params,...xbox};
  await call('preview',rebound);
  const reboundSaved=await call('apply',rebound);
  if (reboundSaved.preset.trigger_mask!==0x2000 || reboundSaved.calibration.device.backend!=='xinput'
      || JSON.stringify(reboundSaved.preset.frost_moon)!==JSON.stringify(preset.frost_moon)) throw new Error('Packaged controller rebinding failed');
  let blocked = false;
  try { await call('enable', params); } catch (error) { blocked = String(error).includes('disabled during the packaged UI check'); }
  if (!blocked) throw new Error('Smoke game isolation failed');
  fs.writeFileSync(report, JSON.stringify({passed:true,...screen,compiledPhases:Object.keys(compiled.moves).length,
    unicode:true,settings:true,bindings:true,customRoutes:true,uiRebinding,incompatiblePopup:true,invalidDraftPreserved:true,xinputRebinding:true,gameAccess:false}, null, 2));
}

module.exports = {runSmoke};
