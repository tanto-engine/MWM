const fs = require('node:fs');
const path = require('node:path');

async function runSmoke(window, call, report) {
  // Exercise the actual packaged renderer and worker without enabling any game feature.
  // A copied EXE must supply its own Python, preset data, artwork and research collection.
  // Saved settings and the report stay beside the explicitly supplied smoke output path.
  const screen = await window.webContents.executeJavaScript(`(async () => {
    const wait = () => new Promise(resolve => setTimeout(resolve, 50));
    for (let i=0;i<200;i++) {
      if (!document.body.inert && document.querySelector('#validation').dataset.state==='valid') break;
      await wait();
    }
    if (document.querySelector('#validation').dataset.state!=='valid') throw new Error(document.querySelector('#notice').textContent);
    const artwork=new Image(); artwork.src=new URL('assets/background.png',location.href).href; await artwork.decode();
    const collection=await window.mwm.request('collection');
    if (!collection.moves.length) throw new Error('Packaged move collection missing');
    return {artwork:[artwork.naturalWidth,artwork.naturalHeight],datasetMoves:collection.moves.length};
  })()`);
  const snapshot = await call('snapshot');
  const preset = await call('starter', {calibration:snapshot.calibration});
  preset.name = 'Packaged check – テスト';
  const params = {...snapshot, preset, nioh_exe:'C:\\Game path test\\nioh.exe'};
  const compiled = await call('preview', params);
  const saved = await call('apply', params);
  if (saved.preset.name !== preset.name || saved.nioh_exe !== params.nioh_exe) throw new Error('Packaged settings roundtrip failed');
  const file = path.join(path.dirname(report), 'smoke-bindings.json');
  await call('binding_export', {...params,group:'frost',path:file});
  const loaded = await call('binding_import', {...params,group:'frost',path:file});
  if (JSON.stringify(loaded.frost_moon) !== JSON.stringify(preset.frost_moon)) throw new Error('Packaged bindings roundtrip failed');
  let blocked = false;
  try { await call('enable', params); } catch (error) { blocked = String(error).includes('disabled during the packaged UI check'); }
  if (!blocked) throw new Error('Smoke game isolation failed');
  fs.writeFileSync(report, JSON.stringify({passed:true,...screen,compiledPhases:Object.keys(compiled.moves).length,
    unicode:true,settings:true,bindings:true,gameAccess:false}, null, 2));
}

module.exports = {runSmoke};
