// The privileged window host owns dialogs and the Engine worker's private pipe.
// The renderer receives only reviewed commands; it has no Node or filesystem access.
const { app, BrowserWindow, dialog, ipcMain } = require('electron');
const { spawn } = require('node:child_process');
const { createInterface } = require('node:readline');
const path = require('node:path');
const fs = require('node:fs');
const root = path.resolve(__dirname, '..');
const methods = new Set(['snapshot', 'validate', 'apply', 'baseline', 'controller', 'capture_start', 'capture_poll', 'capture_cancel', 'enable', 'disable']);
const pending = new Map();
let window, worker, nextId = 0;

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
  // Packaged builds resolve the gate-staged worker; source builds use the sibling Engine.
  const cached = path.join(process.env.USERPROFILE || '', '.cache', 'tanto-build', 'Scripts', 'python.exe');
  const python = process.env.NIOH_PYTHON || (fs.existsSync(cached) ? cached : 'python.exe');
  const executable = app.isPackaged ? path.join(process.resourcesPath, 'worker', 'MWMWorker.exe') : python;
  const args = app.isPackaged ? ['--desktop-worker'] : ['-B', path.join(root, 'app', 'web_worker.py')];
  if (app.isPackaged) fs.mkdirSync(app.getPath('userData'), { recursive: true });
  worker = spawn(executable, args, { cwd: app.isPackaged ? app.getPath('userData') : root, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'] });
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
      reply.error ? entry.reject(new Error(reply.error)) : entry.resolve(reply.result);
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
    }, 15000);
    pending.set(id, { resolve, reject, timer });
    worker.stdin.write(JSON.stringify({ id, method, params }) + '\n');
  });
}

async function request(event, method, params = {}) {
  // Accept requests only from this app's own top-level renderer.
  // Native file dialogs supply import/export paths; arbitrary renderer paths are not honored.
  // Cancellation returns null and leaves both saved and pending settings unchanged.
  if (event.sender !== window.webContents || event.senderFrame !== window.webContents.mainFrame) throw new Error('Unknown window');
  if (method === 'export') {
    const selected = await dialog.showSaveDialog(window, { title: 'Save moveset', defaultPath: path.join(app.getPath('downloads'), 'MWM-moveset.json'), filters: [{ name: 'Moveset', extensions: ['json'] }] });
    return selected.canceled ? null : call('export', { ...params, path: selected.filePath });
  }
  if (method === 'import' || method === 'game_path') {
    const selected = await dialog.showOpenDialog(window, { title: method === 'import' ? 'Load moveset' : 'Select nioh.exe', properties: ['openFile'], filters: [{ name: method === 'import' ? 'Moveset' : 'Nioh', extensions: [method === 'import' ? 'json' : 'exe'] }] });
    if (selected.canceled) return null;
    return method === 'game_path' ? selected.filePaths[0] : call('import', { ...params, path: selected.filePaths[0] });
  }
  if (!methods.has(method)) throw new Error('Unsupported desktop operation');
  return call(method, params);
}

async function openWindow() {
  // Keep local content isolated from Electron's OS privileges.
  // CSS and TypeScript implement the interface; preload exposes one allowlisted request function.
  // External navigation and popups cannot replace this trusted local renderer.
  startWorker();
  window = new BrowserWindow({ width: 1120, height: 840, minWidth: 860, minHeight: 640, backgroundColor: '#11151c', title: 'MWM · Multi-Weapon Moveset Mod', autoHideMenuBar: true, webPreferences: { preload: path.join(__dirname, 'preload.cjs'), contextIsolation: true, sandbox: true, nodeIntegration: false } });
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
}

ipcMain.handle('mwm:request', request);
app.whenReady().then(openWindow);
app.on('window-all-closed', () => {
  // Close the window-owned worker by ending its input stream.
  // Its finalizer releases any temporary binding reader.
  // Explicit Disable remains the only UI request that stops enabled gameplay.
  if (worker) worker.stdin.end();
  app.quit();
});
