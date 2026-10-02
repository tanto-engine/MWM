// Check the installed portable generator and the worker's lifetime without running gameplay.
// Launches need separate extraction folders because either launcher removes its folder on exit.
// The retained worker must still contain its libraries after that temporary source disappears.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const builder = path.join(root, 'node_modules/app-builder-lib');
const source = fs.readFileSync(path.join(builder, 'out/targets/nsis/NsisTarget.js'), 'utf8');
const start = source.indexOf('const { unpackDirName, requestExecutionLevel, splashImage } = options;');
const end = source.indexOf('if (splashImage != null)', start);
assert.ok(start >= 0 && end > start, 'Review changed portable generator before release');
const options = JSON.parse(fs.readFileSync(path.join(root, 'package.json'))).build.portable;
const context = {options, defines:{}, builder_util_1:{generateKsuid:() => 'shared-launch-folder'}};
vm.runInNewContext(source.slice(start, end), context);
assert.equal(context.defines.UNPACK_DIR_NAME, undefined, 'Portable launches share a deletable extraction directory');
assert.ok(fs.readFileSync(path.join(builder, 'templates/nsis/portable.nsi'), 'utf8').includes('StrCpy $INSTDIR "$PLUGINSDIR\\app"'));

const {retainWorker} = require('../desktop/portable_worker.cjs');
const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'mwm-worker-'));
try {
  const source = path.join(folder, 'extraction'), state = path.join(folder, 'state');
  fs.mkdirSync(path.join(source, '_internal'), {recursive:true});
  fs.writeFileSync(path.join(source, 'MWMWorker.exe'), 'worker fixture');
  fs.writeFileSync(path.join(source, '_internal', 'python.dll'), 'library fixture');
  const first = retainWorker(source, state, '0.3.0-alpha.2');
  const copy = fs.cpSync;
  try {
    fs.cpSync = (_source, stage) => {
      fs.writeFileSync(path.join(stage, 'partial-worker'), 'incomplete');
      throw new Error('Simulated disk full');
    };
    assert.throws(() => retainWorker(source, state, '0.3.0-alpha.3'), /Simulated disk full/);
  } finally { fs.cpSync = copy; }
  assert.deepEqual(fs.readdirSync(path.join(state, 'workers')), ['0.3.0-alpha.2'], 'Failed extraction left partial workers behind');
  fs.writeFileSync(path.join(source, 'MWMWorker.exe'), 'next worker');
  const next = retainWorker(source, state, '0.3.0-alpha.3');
  assert.equal(fs.readFileSync(next, 'utf8'), 'next worker');
  // Delete only this owned fixture's simulated extraction; no user runtime is involved.
  // Reopening must reuse a complete cached worker without its original source files.
  // The version key keeps an already-running supervisor's files unchanged.
  fs.rmSync(source, {recursive:true});
  assert.equal(retainWorker(source, state, '0.3.0-alpha.2'), first);
  assert.equal(fs.readFileSync(first, 'utf8'), 'worker fixture');
  assert.equal(fs.readFileSync(path.join(path.dirname(first), '_internal', 'python.dll'), 'utf8'), 'library fixture');
  assert.deepEqual(fs.readdirSync(path.join(state, 'workers')), ['0.3.0-alpha.2', '0.3.0-alpha.3']);
} finally { fs.rmSync(folder, {recursive:true, force:true}); }
