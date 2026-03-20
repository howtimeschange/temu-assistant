'use strict'

const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('api', {
  // 状态
  getStatus: () => ipcRenderer.invoke('get-status'),

  // Chrome CDP
  launchChrome: (path) => ipcRenderer.invoke('launch-chrome', path),
  checkChrome: () => ipcRenderer.invoke('check-chrome'),
  ensureChrome: () => ipcRenderer.invoke('ensure-chrome'),
  getChromePath: () => ipcRenderer.invoke('get-chrome-path'),
  saveChromePath: (p) => ipcRenderer.invoke('save-chrome-path', p),
  browseChromePath: () => ipcRenderer.invoke('browse-chrome-path'),

  // 配置
  getConfig: () => ipcRenderer.invoke('get-config'),
  saveConfig: (cfg) => ipcRenderer.invoke('save-config', cfg),

  // 任务
  runTask: (task, params) => ipcRenderer.invoke('run-task', task, params),
  stopTask: () => ipcRenderer.invoke('stop-task'),

  // 文件
  openOutputDir: () => ipcRenderer.invoke('open-output-dir'),
  getRecentFiles: () => ipcRenderer.invoke('get-recent-files'),
  openFile: (p) => ipcRenderer.invoke('open-file', p),
  showInFinder: (p) => ipcRenderer.invoke('show-in-finder', p),

  // main → renderer 事件
  onLog: (cb) => {
    ipcRenderer.on('log', (_, msg) => cb(msg))
    return () => ipcRenderer.removeAllListeners('log')
  },
  onStatus: (cb) => {
    ipcRenderer.on('status', (_, data) => cb(data))
    return () => ipcRenderer.removeAllListeners('status')
  },
})
