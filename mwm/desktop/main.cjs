// The privileged window host owns dialogs and the Engine worker's private pipe.
// The renderer receives only reviewed commands; it has no Node or filesystem access.
const { app, BrowserWindow, dialog, ipcMain } = require('electron');
const { spawn } = require('node:child_process');
const { createInterface } = require('node:readline');
const path = require('node:path');
const fs = require('node:fs');
const root = path.resolve(__dirname, '..');
const smokeIndex = process.argv.indexOf('--ui-smoke');
const smokeReport = smokeIndex < 0 ? null : path.resolve(process.argv[smokeIndex + 1]);
if (smokeReport) {
  // Smoke mode isolates settings and blocks game/controller access in the worker.
  const state = path.join(path.dirname(smokeReport), 'mwm-smoke-state');
  app.setPath('userData', state);
  process.env.MWM_UI_SMOKE = '1';
  process.env.NIOH_RUNTIME_HOME = path.join(state, 'runtime');
}
const methods = new Set(['snapshot', 'validate', 'preview', 'add_override', 'apply', 'baseline', 'starter', 'trial', 'maria', 'maria_dash', 'controller', 'capture_start', 'capture_poll', 'capture_cancel', 'haptic', 'enable', 'disable', 'preset_list', 'preset_save', 'preset_load', 'preset_delete', 'preset_switch', 'preset_cycle']);
const pending = new Map();
let window, worker, nextId = 0, hotkeyTimer, hotkeyBusy = false, cycling = false, closeAfterCycle = false;

async function switchPreset(method, params = {}) {
  if (cycling) throw new Error('Preset switch already in progress');
  cycling = true;
  try { return await call(method, params); }
  finally {
    cycling = false;
    if (closeAfterCycle && window && !window.isDestroyed()) window.close();
  }
}

function failPending(error) {
  // Reject all waiters and clear their deadlines when the private worker pipe fails.
  for (const { reject, timer } of pending.values()) { clearTimeout(timer); reject(error); }
  pending.clear();
}

function startWorker() {
  // Packaged workers outlive extraction; source builds use the selected development Python.
  const cached = path.join(process.env.USERPROFILE || '', '.cache', 'tanto-build', 'Scripts', 'python.exe');
  const python = process.env.NIOH_PYTHON || (fs.existsSync(cached) ? cached : 'python.exe');
  const version = JSON.parse(fs.readFileSync(path.join(root, 'product.json'), 'utf8')).version;
  const executable = app.isPackaged ? require('./portable_worker.cjs').retainWorker(path.join(process.resourcesPath, 'worker'), app.getPath('userData'), version) : python;
  const args = app.isPackaged ? ['--desktop-worker'] : ['-B', path.join(root, 'app', 'web_worker.py')];
  if (app.isPackaged) fs.mkdirSync(app.getPath('userData'), { recursive: true });
  worker = spawn(executable, args, { cwd: app.isPackaged ? app.getPath('userData') : root, windowsHide: true,
    env: {...process.env, PYINSTALLER_RESET_ENVIRONMENT: '1'}, stdio: ['pipe', 'pipe', 'pipe'] });
  worker.stdin.on('error', error => {
    // A broken pipe must reject requests rather than crash the editor.
    failPending(error);
  });
  let stderr = '';
  worker.stderr.on('data', chunk => {
    // Keep a bounded diagnostic tail; stdout is reserved for protocol replies.
    stderr = (stderr + chunk.toString()).slice(-4000);
  });
  createInterface({ input: worker.stdout }).on('line', line => {
    // Correlate overlapping requests and ignore replies whose deadlines already expired.
    try {
      const reply = JSON.parse(line), entry = pending.get(reply.id);
      if (!entry) return;
      clearTimeout(entry.timer); pending.delete(reply.id);
      reply.error ? entry.reject(Object.assign(new Error(reply.error.message), { kind: reply.error.kind })) : entry.resolve(reply.result);
    } catch (error) { failPending(new Error('Invalid Engine worker response: ' + error.message)); }
  });
  worker.on('error', error => {
    failPending(error);
  });
  worker.on('exit', code => {
    // Only the editor worker exits here; gameplay has a separate lifecycle owner.
    worker = null;
    failPending(new Error(stderr || 'Engine worker exited (' + code + ')'));
  });
}

function call(method, params = {}) {
  // Bound each request independently so a stalled worker cannot leave the UI inert forever.
  if (!worker || !worker.stdin.writable) return Promise.reject(new Error('Engine worker unavailable; reopen MWM'));
  return new Promise((resolve, reject) => {
    const id = ++nextId;
    const timer = setTimeout(() => {
      pending.delete(id); reject(new Error('Engine timed out: ' + method));
    }, method === 'preset_cycle' || method === 'preset_switch' ? 60000 : 15000);
    pending.set(id, { resolve, reject, timer });
    worker.stdin.write(JSON.stringify({ id, method, params }) + '\n');
  });
}

async function request(event, method, params = {}) {
  // Trust only the local main frame. File paths must come from native dialogs.
  if (event.sender !== window.webContents || event.senderFrame !== window.webContents.mainFrame) throw new Error('Unknown window');
  if (method === 'export' || method === 'binding_export') {
    const group = method === 'binding_export';
    const selected = await dialog.showSaveDialog(window, { title: group ? 'Save binding group' : 'Save moveset', defaultPath: path.join(app.getPath('downloads'), group ? 'MWM-bindings.json' : 'MWM-moveset.json'), filters: [{ name: group ? 'Binding group' : 'Moveset', extensions: ['json'] }] });
    return selected.canceled ? null : call(method, { ...params, path: selected.filePath });
  }
  if (method === 'import' || method === 'binding_import' || method === 'game_path') {
    const game = method === 'game_path';
    const selected = await dialog.showOpenDialog(window, { title: game ? 'Select nioh.exe' : method === 'binding_import' ? 'Load binding group' : 'Load moveset', properties: ['openFile'], filters: [{ name: game ? 'Nioh' : 'Configuration', extensions: [game ? 'exe' : 'json'] }] });
    if (selected.canceled) return null;
    return game ? selected.filePaths[0] : call(method, { ...params, path: selected.filePaths[0] });
  }
  if (method === 'collection') return JSON.parse(fs.readFileSync(path.join(__dirname, 'collection.json'), 'utf8'));
  if (!methods.has(method)) throw new Error('Unsupported desktop operation');
  if (method === 'preset_cycle' || method === 'preset_switch') return switchPreset(method, params);
  return call(method, params);
}

async function openWindow() {
  // Preload is the sole bridge from the sandboxed renderer to OS privileges.
  startWorker();
  window = new BrowserWindow({ show: !smokeReport, width: 1120, height: 840, minWidth: 860, minHeight: 640, backgroundColor: '#11151c', title: 'MWM · Multi-Weapon Moveset Mod', autoHideMenuBar: true, webPreferences: { preload: path.join(__dirname, 'preload.cjs'), contextIsolation: true, sandbox: true, nodeIntegration: false, backgroundThrottling: !smokeReport } });
  window.on('close', event => {
    if (cycling) { event.preventDefault(); closeAfterCycle = true; window.hide(); }
  });
  window.webContents.setWindowOpenHandler(() => {
    return { action: 'deny' };
  });
  window.webContents.on('will-navigate', event => {
    event.preventDefault();
  });
  await window.loadFile(path.join(__dirname, 'index.html'));
  if (!smokeReport) {
    // Poll the distinct DS4 WinMM touchpad bit from the main process, including while unfocused.
    // The worker serializes requests, so at most one cycle can run at a time.
    hotkeyTimer = setInterval(async () => {
      if (hotkeyBusy || !worker) return;
      hotkeyBusy = true;
      try {
        if (await call('preset_hotkey_poll')) {
          try { window.webContents.send('mwm:preset-cycle', { result: await switchPreset('preset_cycle') }); }
          catch (error) { window.webContents.send('mwm:preset-cycle', { error: error.message }); }
        }
      } catch { /* A closed worker is reported by ordinary editor requests. */ }
      finally { hotkeyBusy = false; }
    }, 50);
  }
  if (smokeReport) {
    await require('./smoke.cjs').runSmoke(window, call, smokeReport);
    const child = worker; worker = null;
    await new Promise(resolve => {
      // Wait for the smoke worker to release files before the gate removes its isolated state.
      child.once('exit', resolve); child.stdin.end();
    });
    app.exit(0);
  }
}

ipcMain.handle('mwm:request', async (...args) => {
  // Preserve validation identity without Electron's internal IPC error wrapper.
  try { return { ok: true, result: await request(...args) }; }
  catch (error) { return { ok: false, error: { kind: error.kind || 'operation', message: error.message } }; }
});
if (!app.requestSingleInstanceLock()) app.quit();
else {
  app.on('second-instance', () => {
    if (window) { if (window.isMinimized()) window.restore(); window.show(); window.focus(); }
  });
  app.whenReady().then(openWindow).catch(error => {
    if (smokeReport) fs.writeFileSync(smokeReport, JSON.stringify({passed:false,error:String(error)}));
    else dialog.showErrorBox('MWM could not start', String(error));
    app.exit(1);
  });
}
app.on('window-all-closed', () => {
  // Closing the editor releases capture but leaves gameplay under its separate supervisor.
  clearInterval(hotkeyTimer);
  if (worker) worker.stdin.end();
  app.quit();
});
