const { contextBridge, ipcRenderer } = require('electron');

// Expose protected methods to renderer
contextBridge.exposeInMainWorld('electronAPI', {
    selectFile: () => ipcRenderer.invoke('select-file'),
    selectFolder: () => ipcRenderer.invoke('select-folder'),
    startBackend: () => ipcRenderer.invoke('start-backend'),
    stopBackend: () => ipcRenderer.invoke('stop-backend'),
    getAppPath: () => ipcRenderer.invoke('get-app-path'),
    openPath: (path) => ipcRenderer.invoke('open-path', path),
    getApiToken: () => ipcRenderer.invoke('get-api-token'),
    // One-shot events: use .once() to prevent duplicate listeners on reload
    onApiToken: (callback) => ipcRenderer.once('api-token', (_event, token) => callback(token)),
    onBackendReady: (callback) => ipcRenderer.once('backend-ready', (_event) => callback()),
    // Persistent event: provide both subscribe and unsubscribe to prevent leaks
    onBackendLog: (callback) => {
        const handler = (_event, msg) => callback(msg);
        ipcRenderer.on('backend-log', handler);
        // Return unsubscribe function so renderer can clean up
        return () => ipcRenderer.removeListener('backend-log', handler);
    },
});
