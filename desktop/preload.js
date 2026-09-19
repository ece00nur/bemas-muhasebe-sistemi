// Context-isolated bridge: the renderer never gets raw Node/Electron access,
// only this one narrow function used by setup.html to save the backend
// server address the first time the app runs on a new computer.
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("bemasSetup", {
  testAndSaveServerUrl: (url) => ipcRenderer.invoke("bemas:test-and-save-server-url", url),
});
