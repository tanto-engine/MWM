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
  // Keep packaged verification away from user settings and any registered game session.
  // The worker rejects lifecycle/controller calls in this mode even if renderer behavior regresses.
  // Only the caller-selected report directory receives test state.
  const state = path.join(path.dirname(smokeReport), 'mwm-smoke-state');
  app.setPath('userData', state);
  process.env.MWM_UI_SMOKE = '1';
  process.env.NIOH_RUNTIME_HOME = path.join(state, 'runtime');
}
const methods = new Set(['snapshot', 'validate', 'preview', 'add_override', 'apply', 'baseline', 'starter', 'trial', 'controller', 'capture_start', 'capture_poll', 'capture_cancel', 'haptic', 'enable', 'disable', 'preset_list', 'preset_save', 'preset_load', 'preset_delete', 'preset_switch', 'preset_cycle']);
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
  // Resolve every waiting screen operation when its worker is no longer available.
  // Clear individual timers so old failures cannot overwrite a later request.
  // Show the actual failure instead of leaving Apply apparently busy forever.
  for (const { reject, timer } of pending.values()) { clearTimeout(timer); reject(error); }
  pending.clear();
}

function startWorker() {
  // Use an explicit development Python override or the interpreter on PATH.
  // Engine remains a separate worker; frame-sensitive gameplay never runs in Chromium.
  // Packaged builds resolve the gate-staged worker; source builds use this repository's Engine.
  const cached = path.join(process.env.USERPROFILE || '', '.cache', 'tanto-build', 'Scripts', 'python.exe');
  const python = process.env.NIOH_PYTHON || (fs.existsSync(cached) ? cached : 'python.exe');
  const version = JSON.parse(fs.readFileSync(path.join(root, 'product.json'), 'utf8')).version;
  const executable = app.isPackaged ? require('./portable_worker.cjs').retainWorker(path.join(process.resourcesPath, 'worker'), app.getPath('userData'), version) : python;
  const args = app.isPackaged ? ['--desktop-worker'] : ['-B', path.join(root, 'app', 'web_worker.py')];
  if (app.isPackaged) fs.mkdirSync(app.getPath('userData'), { recursive: true });
  worker = spawn(executable, args, { cwd: app.isPackaged ? app.getPath('userData') : root, windowsHide: true,
    env: {...process.env, PYINSTALLER_RESET_ENVIRONMENT: '1'}, stdio: ['pipe', 'pipe', 'pipe'] });
  worker.stdin.on('error', error => {
    // A closed worker pipe must fail the current request instead of crashing Electron.
    // Pending promises share the same bounded error path as worker exit.
    // Engine's separately owned gameplay process is unaffected.
    failPending(error);
  });
  let stderr = '';
  worker.stderr.on('data', chunk => {
    // Retain a bounded error tail for startup/import failures.
    // Diagnostics never share the protocol's stdout channel.
    // The UI receives the failure only if its worker exits.
    stderr = (stderr + chunk.toString()).slice(-4000);
  });
  createInterface({ input: worker.stdout }).on('line', line => {
    // Match replies by ID so status reads and form actions cannot cross wires.
    // Ignore late replies whose timed-out request has already left the map.
    // Invalid protocol data terminates the bridge visibly instead of being treated as state.
    try {
      const reply = JSON.parse(line), entry = pending.get(reply.id);
      if (!entry) return;
      clearTimeout(entry.timer); pending.delete(reply.id);
      reply.error ? entry.reject(Object.assign(new Error(reply.error.message), { kind: reply.error.kind })) : entry.resolve(reply.result);
    } catch (error) { failPending(new Error('Invalid Engine worker response: ' + error.message)); }
  });
  worker.on('error', error => {
    // A missing interpreter is a startup failure, not a missing-controller status.
    // Reject requests immediately with the concrete OS error.
    // No gameplay process is killed by this bridge failure.
    failPending(error);
  });
  worker.on('exit', code => {
    // Mark the bridge unavailable once its owned process exits.
    // Include the bounded Python traceback when initialization failed.
    // Existing Engine gameplay stays under its own lifecycle owner.
    worker = null;
    failPending(new Error(stderr || 'Engine worker exited (' + code + ')'));
  });
}

function call(method, params = {}) {
  // Send only JSON-serializable configuration requests on the private worker pipe.
  // A deadline makes a stalled worker an explicit UI failure.
  // Request IDs are local counters and never game object addresses.
  if (!worker || !worker.stdin.writable) return Promise.reject(new Error('Engine worker unavailable; reopen MWM'));
  return new Promise((resolve, reject) => {
    // Keep the promise's cancellation timer beside its reply callbacks.
    // Late responses cannot apply UI state after a timeout.
    // Serialization leaves the Engine responsible for semantic validation.
    const id = ++nextId;
    const timer = setTimeout(() => {
      // Drop only this unresponsive request.
      // Other in-flight reads retain their own correlation IDs.
      // Report the method so the user knows which operation failed.
      pending.delete(id); reject(new Error('Engine timed out: ' + method));
    }, method === 'preset_cycle' || method === 'preset_switch' ? 60000 : 15000);
    pending.set(id, { resolve, reject, timer });
    worker.stdin.write(JSON.stringify({ id, method, params }) + '\n');
  });
}

async function request(event, method, params = {}) {
  // Accept requests only from this app's own top-level renderer.
  // Native file dialogs supply import/export paths; arbitrary renderer paths are not honored.
  // Cancellation returns null and leaves both saved and pending settings unchanged.
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
  // Keep local content isolated from Electron's OS privileges.
  // CSS and TypeScript implement the interface; preload exposes one allowlisted request function.
  // External navigation and popups cannot replace this trusted local renderer.
  startWorker();
  window = new BrowserWindow({ show: !smokeReport, width: 1120, height: 840, minWidth: 860, minHeight: 640, backgroundColor: '#11151c', title: 'MWM · Multi-Weapon Moveset Mod', autoHideMenuBar: true, webPreferences: { preload: path.join(__dirname, 'preload.cjs'), contextIsolation: true, sandbox: true, nodeIntegration: false, backgroundThrottling: !smokeReport } });
  window.on('close', event => {
    if (cycling) { event.preventDefault(); closeAfterCycle = true; window.hide(); }
  });
  window.webContents.setWindowOpenHandler(() => {
    // No application action requires a second browser window.
    // Block script-created windows before they receive navigation context.
    // File selection remains a native main-process dialog.
    return { action: 'deny' };
  });
  window.webContents.on('will-navigate', event => {
    // Keep this window on the bundled interface.
    // Renderer hyperlinks never navigate to remote privileged content.
    // The application has no remote web dependency.
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
      // Let the checked worker close its pipe before the gate removes isolated test files.
      // Later renderer polls see an unavailable bridge rather than writing to a closing stream.
      // This shuts down only the editor worker; smoke mode never starts gameplay.
      child.once('exit', resolve); child.stdin.end();
    });
    app.exit(0);
  }
}

ipcMain.handle('mwm:request', async (...args) => {
  // Send failures as data so Electron cannot prepend its internal IPC exception wrapper.
  // Validation keeps its identity through the isolated preload boundary.
  // Worker startup and filesystem failures remain ordinary operation errors.
  try { return { ok: true, result: await request(...args) }; }
  catch (error) { return { ok: false, error: { kind: error.kind || 'operation', message: error.message } }; }
});
if (!app.requestSingleInstanceLock()) app.quit();
else {
  app.on('second-instance', () => {
    // Reopening focuses the existing editor instead of starting another configuration worker.
    // Gameplay remains owned by Engine's separate supervisor lock.
    // Portable launches still extract privately before they reach this callback.
    if (window) { if (window.isMinimized()) window.restore(); window.show(); window.focus(); }
  });
  app.whenReady().then(openWindow).catch(error => {
    // Report packaged startup failures and terminate without a misleading empty editor.
    // Automated smoke mode writes diagnostics without showing a blocking error dialog.
    // Normal launches show the concrete failure to the user.
    if (smokeReport) fs.writeFileSync(smokeReport, JSON.stringify({passed:false,error:String(error)}));
    else dialog.showErrorBox('MWM could not start', String(error));
    app.exit(1);
  });
}
app.on('window-all-closed', () => {
  // Close the window-owned worker by ending its input stream.
  // Its finalizer releases any temporary binding reader.
  // Explicit Disable remains the only UI request that stops enabled gameplay.
  clearInterval(hotkeyTimer);
  if (worker) worker.stdin.end();
  app.quit();
});
