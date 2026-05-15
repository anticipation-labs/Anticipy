// Empty preload bridge for now — the renderer is purely informational
// (shows status of the CDP attach + Realtime subscriber). Future iterations
// can expose IPC helpers for "pause executor" / "resume executor" buttons.

const { contextBridge } = require('electron');

contextBridge.exposeInMainWorld('anticipy', {
  version: '0.1.0',
});
