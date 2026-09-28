// A gameplay supervisor may outlive the editor and NSIS's temporary extraction directory.
// Keep each immutable release's worker in app data; publishing never replaces an in-use version.
const fs = require('node:fs');
const path = require('node:path');

function retainWorker(source, directory, version) {
  // Copy the complete embedded worker, including Python, data and native DLLs.
  // An atomic directory rename makes only complete copies visible to later launches.
  // The app's single-instance lock serializes publication; old versions remain usable by live supervisors.
  const store = path.join(directory, 'workers'), target = path.join(store, version);
  if (!fs.existsSync(target)) {
    fs.mkdirSync(store, {recursive:true});
    const stage = fs.mkdtempSync(path.join(store, '.stage-'));
    fs.cpSync(source, stage, {recursive:true});
    fs.renameSync(stage, target);
  }
  return path.join(target, 'MWMWorker.exe');
}

module.exports = {retainWorker};
