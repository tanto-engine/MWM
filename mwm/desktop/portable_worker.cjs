// A gameplay supervisor may outlive the editor and NSIS's temporary extraction directory.
// Keep each immutable release's worker in app data; publishing never replaces an in-use version.
const fs = require('node:fs');
const path = require('node:path');

function retainWorker(source, directory, version) {
  // Publish complete workers atomically under the app's single-instance lock.
  // Live supervisors retain their previous immutable version.
  const store = path.join(directory, 'workers'), target = path.join(store, version);
  if (!fs.existsSync(target)) {
    fs.mkdirSync(store, {recursive:true});
    const stage = fs.mkdtempSync(path.join(store, '.stage-'));
    try {
      fs.cpSync(source, stage, {recursive:true});
      fs.renameSync(stage, target);
    } catch (error) {
      // Keep the extraction error if the OS also prevents temporary-file cleanup.
      try { fs.rmSync(stage, {recursive:true, force:true}); } catch {}
      throw error;
    }
  }
  return path.join(target, 'MWMWorker.exe');
}

module.exports = {retainWorker};
