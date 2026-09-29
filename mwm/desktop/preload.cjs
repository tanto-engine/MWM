// This is the complete renderer privilege surface: one request channel, no Node handles.
const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('mwm', {
  async request(method, params) {
    // Forward a named operation to the main-process allowlist.
    // Values are structured-cloned; the renderer never receives worker or filesystem handles.
    // Main-process dialogs and Engine validators remain the final authority.
    const reply = await ipcRenderer.invoke('mwm:request', method, params);
    if (!reply.ok) throw reply.error;
    return reply.result;
  },
  onPresetCycle(callback) {
    // One scoped listener reports background controller switches without changing the editor draft.
    const listener = (_event, value) => callback(value);
    ipcRenderer.on('mwm:preset-cycle', listener);
    return () => ipcRenderer.removeListener('mwm:preset-cycle', listener);
  }
});
