// Run the actual desktop command handlers with fake Electron/process boundaries.
// No game, real shortcut, application window or user recording is touched.
// Engine's existing ProductBoundaryTests owns this focused regression harness.
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const assert = require('node:assert/strict');
const { createRequire } = require('node:module');
const { EventEmitter } = require('node:events');
const { PassThrough } = require('node:stream');
const repository = path.resolve(__dirname, '../../../tanto-recorder');
const localRequire = createRequire(path.join(repository, 'package.json'));
const source = fs.readFileSync(path.join(repository, 'desktop/main.ts'), 'utf8') + `
globalThis.harness = { command, shortcut, setHotkey, view,
  initialize(value, fakeWindow) { settings = value; window = fakeWindow; },
  done() { return workerDone; } };`;
const code = localRequire('esbuild').buildSync({ stdin: { contents: source, loader: 'ts',
  resolveDir: path.join(repository, 'desktop') }, bundle: true, platform: 'node', format: 'cjs',
  external: ['electron', 'node:child_process'], write: false }).outputFiles[0].text;

function fixture(name, packaged = false) {
  // Give each scenario its own settings/library and the real storage implementation.
  // Fake process streams retain normal asynchronous launch/close behavior.
  // Capture registered callbacks locally; no Windows shortcut registration occurs.
  const root = path.join(process.argv[2], name), registrations = new Map(), children = [];
  fs.mkdirSync(root, { recursive: true });
  const electron = { app: { isPackaged: packaged, getPath: () => root,
    requestSingleInstanceLock: () => true, whenReady: () => new Promise(() => {}), on() {} },
    globalShortcut: { register(key, callback) { if (registrations.has(key)) return false; registrations.set(key, callback); return true; },
      unregister(key) { registrations.delete(key); }, isRegistered(key) { return registrations.has(key); } } };
  const spawn = () => {
    const child = new EventEmitter();
    child.stdout = new PassThrough(); child.stderr = new PassThrough(); child.stdin = new PassThrough();
    child.stdin.on('data', () => queueMicrotask(() => child.emit('close', 0)));
    children.push(child); return child;
  };
  const context = { require: name => name === 'electron' ? electron : name === 'node:child_process' ? { spawn } : localRequire(name),
    __dirname: path.join(repository, 'desktop-dist'), module: { exports: {} }, exports: {},
    process: { argv: [], env: { TANTO_STATE_ROOT: root }, resourcesPath: path.join(root, 'resources') },
    console, setTimeout, clearTimeout, setInterval, Buffer, queueMicrotask };
  vm.runInNewContext(code, context);
  const api = context.harness;
  api.initialize({ recordings_directory: path.join(root, 'Recordings'), hotkey: 'Off', cue_volume: 40,
    tutorial_version: 4, motion: false, boss_draft: '' },
    { isDestroyed: () => false, webContents: { isDestroyed: () => false, send() {} } });
  return { api, root, registrations, children };
}

async function changedBoss() {
  // Enter a description for Jin, then change context before describing a different boss.
  // New notes must belong to the new encounter rather than overwriting Jin's draft.
  // The old session remains on disk with its original boss and text.
  const { api } = fixture('boss');
  await api.command('draft', { boss: 'Jin Hayabusa', text: 'Original Jin draft' });
  const old = api.view().folder;
  await api.command('context', 'Tachibana Muneshige');
  await api.command('draft', { boss: 'Tachibana Muneshige', text: 'New boss move' });
  assert.equal(api.view().session.boss_name, 'Tachibana Muneshige');
  assert.equal(JSON.parse(fs.readFileSync(path.join(old, 'encounter.json'))).draft.text, 'Original Jin draft');
}

async function hotkey() {
  // Bind F2 and invoke the registered callback as Electron would, without sending keys.
  // Verify Start uses the latest boss and the same callback cooperatively stops its worker.
  // Cancelling a rebind must restore the saved shortcut and unblock recording.
  const { api, registrations, children } = fixture('hotkey');
  api.setHotkey('F2');
  await api.command('context', 'Tachibana Muneshige');
  registrations.get('F2')();
  assert.equal(children.length, 1);
  assert.equal(api.view().session.boss_name, 'Tachibana Muneshige');
  registrations.get('F2')(); await api.done();
  assert.equal(api.view().running, false);
  await api.command('bind-start'); await api.command('bind-cancel');
  assert.equal(registrations.has('F2'), true);
  registrations.delete('F2'); api.setHotkey('F2');
  assert.equal(registrations.has('F2'), true);
}

async function contextCommit() {
  // Leaving the boss field must detach the previous session without relabeling its evidence.
  // Do not create an empty folder merely for changing an encounter name.
  // Subsequent controls and the global shortcut must see the same committed name.
  const { api } = fixture('context-commit');
  await api.command('draft', { boss: 'Jin Hayabusa', text: 'Keep this draft' });
  const old = api.view().folder;
  await api.command('context-commit', 'Tachibana Muneshige');
  assert.equal(api.view().folder, null);
  assert.equal(api.view().settings.boss_draft, 'Tachibana Muneshige');
  assert.equal(JSON.parse(fs.readFileSync(path.join(old, 'encounter.json'))).boss_name, 'Jin Hayabusa');
}

async function portableIsolation() {
  // Inspect the installed generator's actual option branch before any installer is compiled.
  // Its pinned boolean behavior differs from its documentation, so verify the emitted NSIS definition.
  // Omitting UNPACK_DIR_NAME selects each launch's private $PLUGINSDIR/app in portable.nsi.
  const builder = path.join(repository, 'node_modules/app-builder-lib');
  const source = fs.readFileSync(path.join(builder, 'out/targets/nsis/NsisTarget.js'), 'utf8');
  const start = source.indexOf('const { unpackDirName, requestExecutionLevel, splashImage } = options;');
  const end = source.indexOf('if (splashImage != null)', start);
  assert.ok(start >= 0 && end > start, 'Review the changed portable generator before release');
  const options = JSON.parse(fs.readFileSync(path.join(repository, 'package.json'))).build.portable;
  const context = { options, defines: {}, builder_util_1: { generateKsuid: () => 'shared-build-folder' } };
  vm.runInNewContext(source.slice(start, end), context);
  assert.equal(context.defines.UNPACK_DIR_NAME, undefined, 'Portable launches share a deletable runtime directory');
  assert.ok(fs.readFileSync(path.join(builder, 'templates/nsis/portable.nsi'), 'utf8').includes('StrCpy $INSTDIR "$PLUGINSDIR\\app"'));
}

async function missingWorker() {
  // Model the observed missing portable worker before any capture process exists.
  // Require a useful relaunch error before creating an empty failed take.
  // The real spawn boundary must never be reached with a missing embedded executable.
  const { api, children } = fixture('missing-worker', true);
  await assert.rejects(api.command('toggle', 'Jin Hayabusa'), /worker.*missing|missing.*worker/i);
  assert.equal(children.length, 0);
  assert.equal(api.view().session, null);
}

(async () => {
  const results = [];
  for (const check of [changedBoss, contextCommit, hotkey, missingWorker, portableIsolation]) {
    try { await check(); results.push({ name: check.name, passed: true }); }
    catch (error) { results.push({ name: check.name, passed: false, error: String(error) }); }
  }
  console.log(JSON.stringify(results));
  process.exitCode = results.every(result => result.passed) ? 0 : 1;
})();
