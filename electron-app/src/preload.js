'use strict'

const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('api', {
  // Status
  getStatus: () => ipcRenderer.invoke('get-status'),

  // Daemon & Chrome
  startDaemon: () => ipcRenderer.invoke('start-daemon'),
  launchChrome: (customPath) => ipcRenderer.invoke('launch-chrome', customPath),
  checkChrome: () => ipcRenderer.invoke('check-chrome'),
  getChromePath: () => ipcRenderer.invoke('get-chrome-path'),
  saveChromePath: (p) => ipcRenderer.invoke('save-chrome-path', p),
  browseChromePath: () => ipcRenderer.invoke('browse-chrome-path'),

  // Scrape
  runOnce: () => ipcRenderer.invoke('run-once'),
  stopRun: () => ipcRenderer.invoke('stop-run'),
  startLoop: (intervalMinutes) => ipcRenderer.invoke('start-loop', intervalMinutes),
  stopLoop: () => ipcRenderer.invoke('stop-loop'),

  // Config
  getConfig: () => ipcRenderer.invoke('get-config'),
  saveConfig: (cfg) => ipcRenderer.invoke('save-config', cfg),

  // Files
  openDataDir: () => ipcRenderer.invoke('open-data-dir'),
  getRecentFiles: () => ipcRenderer.invoke('get-recent-files'),
  openFile: (p) => ipcRenderer.invoke('open-file', p),
  showInFinder: (p) => ipcRenderer.invoke('show-in-finder', p),

  // Cron tasks
  cronList: () => ipcRenderer.invoke('cron-list'),
  cronAdd: (entry) => ipcRenderer.invoke('cron-add', entry),
  cronDelete: (index) => ipcRenderer.invoke('cron-delete', index),

  // Events from main → renderer
  onLog: (cb) => {
    ipcRenderer.on('log', (_, msg) => cb(msg))
    return () => ipcRenderer.removeAllListeners('log')
  },
  onStatus: (cb) => {
    ipcRenderer.on('status', (_, data) => cb(data))
    return () => ipcRenderer.removeAllListeners('status')
  },
})
