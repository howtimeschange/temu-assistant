'use strict'

// Unset ELECTRON_RUN_AS_NODE so that child processes we spawn (bb-browser, Python)
// do not accidentally inherit this flag and run in Node-only mode.
delete process.env.ELECTRON_RUN_AS_NODE

const { app, BrowserWindow, ipcMain, shell, dialog } = require('electron')
const path = require('path')
const fs = require('fs')
const net = require('net')
const { spawn, execSync } = require('child_process')

// ── Path helpers ──────────────────────────────────────────────────────────────
function isPkg() { return app.isPackaged }

function getPythonBin() {
  if (isPkg()) {
    const winBin  = path.join(process.resourcesPath, 'python', 'python.exe')
    const unixBin = path.join(process.resourcesPath, 'python', 'bin', 'python3')
    return process.platform === 'win32' ? winBin : unixBin
  }
  // dev: prefer project venv if it exists
  const venvPy = path.join(__dirname, '..', '..', 'venv', 'bin', 'python3')
  if (fs.existsSync(venvPy)) return venvPy
  return process.platform === 'win32' ? 'python' : 'python3'
}

function getPythonScriptsDir() {
  if (isPkg()) {
    return path.join(process.resourcesPath, 'python-scripts')
  }
  // dev: electron-app/src/main.js → project root is two levels up
  return path.join(__dirname, '..', '..')
}

function getBbDaemonScript() {
  if (isPkg()) {
    return path.join(process.resourcesPath, 'bb-browser', 'dist', 'cli.js')
  }
  return path.join(__dirname, '..', 'node_modules', 'bb-browser', 'dist', 'cli.js')
}

function getNodeBin() {
  if (!isPkg()) {
    try {
      const which = require('child_process').execSync('which node', { encoding: 'utf8' }).trim()
      if (which) return which
    } catch (_) {}
    if (process.platform === 'win32') {
      try {
        const which = require('child_process').execSync('where node', { encoding: 'utf8' }).split('\n')[0].trim()
        if (which) return which
      } catch (_) {}
    }
  }
  return process.execPath  // Used with ELECTRON_RUN_AS_NODE=1
}

function nodeNeedsElectronFlag() {
  return getNodeBin() === process.execPath
}

// ── Window ────────────────────────────────────────────────────────────────────
let mainWindow = null

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 780,
    minWidth: 960,
    minHeight: 640,
    titleBarStyle: 'hiddenInset',
    backgroundColor: '#0f1117',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'))

  if (!isPkg()) {
    mainWindow.webContents.openDevTools({ mode: 'detach' })
  }

  mainWindow.on('closed', () => { mainWindow = null })
}

// ── Adapter 安装 ──────────────────────────────────────────────────────────────
// bb-browser 的 `site` 命令只认 ~/.bb-browser/sites/ 目录。
// 把 temu adapters 复制到 ~/.bb-browser/sites/temu/
function installAdapters() {
  try {
    const os = require('os')
    const bbSitesDir = path.join(os.homedir(), '.bb-browser', 'sites')
    fs.mkdirSync(bbSitesDir, { recursive: true })

    const adaptersSrc = isPkg()
      ? path.join(process.resourcesPath, 'python-scripts', 'adapters')
      : path.join(__dirname, '..', '..', 'adapters')

    if (!fs.existsSync(adaptersSrc)) {
      log(`[warn] adapters 源目录不存在：${adaptersSrc}`)
      return
    }

    function copyDir(src, dest) {
      fs.mkdirSync(dest, { recursive: true })
      for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
        const srcPath = path.join(src, entry.name)
        const destPath = path.join(dest, entry.name)
        if (entry.isDirectory()) {
          copyDir(srcPath, destPath)
        } else if (entry.name.endsWith('.js')) {
          fs.copyFileSync(srcPath, destPath)
        }
      }
    }

    copyDir(adaptersSrc, bbSitesDir)
    log(`[ok] adapters 已安装到 ${bbSitesDir}`)
  } catch (e) {
    log(`[warn] 安装 adapters 失败：${e.message}`)
  }
}

app.whenReady().then(async () => {
  createWindow()
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })

  // 安装 temu adapters 到 ~/.bb-browser/sites/temu/
  installAdapters()

  // 启动 FastAPI 后端
  await startBackend()

  // 自动启动 Chrome（CDP 模式）
  log('[chrome] 正在自动启动 Chrome 调试模式…')
  const chromeResult = await launchChrome()
  log(`[chrome] ${chromeResult.msg}`)

  // bb-browser 直接 CLI 模式，无需 daemon
  daemonReady = true
  sendStatus('daemon', true)
  log('[ok] bb-browser 已就绪（直接 CLI 模式）')
})

app.on('window-all-closed', () => {
  stopBackend()
  if (process.platform !== 'darwin') app.quit()
})

// ── Backend server (FastAPI) ──────────────────────────────────────────────────
let backendProcess = null
const BACKEND_PORT = 7788

function getBackendScript() {
  if (isPkg()) {
    return path.join(process.resourcesPath, 'backend', 'server.py')
  }
  return path.join(__dirname, '..', 'backend', 'server.py')
}

async function startBackend() {
  if (await probeTcp(BACKEND_PORT)) {
    log(`[ok] Backend server 已在端口 ${BACKEND_PORT} 运行`)
    return
  }

  const pythonBin = getPythonBin()
  const serverScript = getBackendScript()

  if (!fs.existsSync(serverScript)) {
    log(`[warn] Backend server 脚本未找到：${serverScript}`)
    return
  }

  log(`[backend] 启动: ${pythonBin} ${serverScript} ${BACKEND_PORT}`)
  backendProcess = spawn(pythonBin, [serverScript, String(BACKEND_PORT)], {
    cwd: getPythonScriptsDir(),
    stdio: ['ignore', 'pipe', 'pipe'],
    env: {
      ...process.env,
      PYTHONIOENCODING: 'utf-8',
      PYTHONUTF8: '1',
      ELECTRON_RESOURCES_PATH: isPkg() ? process.resourcesPath : '',
      ELECTRON_BB_BROWSER_SCRIPT: getBbDaemonScript(),
      ELECTRON_NODE_BIN: getNodeBin(),
      ELECTRON_NODE_NEEDS_FLAG: nodeNeedsElectronFlag() ? '1' : '',
    },
  })

  backendProcess.stdout.on('data', d =>
    d.toString('utf8').split('\n').filter(l => l.trim()).forEach(l => log(`[backend] ${l}`))
  )
  backendProcess.stderr.on('data', d =>
    d.toString('utf8').split('\n').filter(l => l.trim()).forEach(l => log(`[backend] ${l}`))
  )
  backendProcess.on('exit', code => {
    log(`[backend] 进程退出，code=${code}`)
    backendProcess = null
  })

  for (let i = 0; i < 20; i++) {
    await new Promise(r => setTimeout(r, 500))
    if (await probeTcp(BACKEND_PORT)) {
      log(`[ok] Backend server 已就绪（端口 ${BACKEND_PORT}）`)
      return
    }
  }
  log(`[warn] Backend server 启动超时`)
}

function stopBackend() {
  if (backendProcess) {
    if (process.platform === 'win32') {
      try { execSync(`taskkill /F /T /PID ${backendProcess.pid}`, { timeout: 3000 }) } catch (_) {}
    } else {
      backendProcess.kill('SIGTERM')
    }
    backendProcess = null
  }
}

// ── Utils ─────────────────────────────────────────────────────────────────────
let daemonReady = false

function probeTcp(port, host = '127.0.0.1', timeoutMs = 500) {
  return new Promise((resolve) => {
    const sock = new net.Socket()
    const done = (ok) => { try { sock.destroy() } catch (_) {} resolve(ok) }
    sock.setTimeout(timeoutMs)
    sock.once('connect', () => done(true))
    sock.once('error', () => done(false))
    sock.once('timeout', () => done(false))
    sock.connect(port, host)
  })
}

// ── Chrome CDP management ─────────────────────────────────────────────────────
const CDP_PORT = 9222

async function checkChromeCdp(port = CDP_PORT) {
  const ok = await probeTcp(port)
  sendStatus('chrome', ok)
  return ok
}

async function launchChrome(port = CDP_PORT, customPath = '') {
  const isWin = process.platform === 'win32'
  const CHROME_PATHS = isWin ? [
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
    process.env.LOCALAPPDATA
      ? `${process.env.LOCALAPPDATA}\\Google\\Chrome\\Application\\chrome.exe`
      : '',
    process.env.PROGRAMFILES
      ? `${process.env.PROGRAMFILES}\\Google\\Chrome\\Application\\chrome.exe`
      : '',
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
    'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
  ].filter(Boolean) : [
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
  ]

  let chromePath = null
  if (customPath && fs.existsSync(customPath)) {
    chromePath = customPath
  } else {
    for (const p of CHROME_PATHS) {
      if (fs.existsSync(p)) { chromePath = p; break }
    }
  }

  if (!chromePath) {
    const filters = isWin
      ? [{ name: 'Executable', extensions: ['exe'] }]
      : [{ name: 'Application', extensions: ['app', ''] }]
    const result = await dialog.showOpenDialog(mainWindow, {
      title: '找不到 Chrome，请手动选择浏览器可执行文件',
      buttonLabel: '选择',
      filters,
      properties: ['openFile'],
    })
    if (result.canceled || !result.filePaths.length) {
      return { ok: false, msg: '未选择浏览器路径，已取消' }
    }
    chromePath = result.filePaths[0]
    saveChromePath(chromePath)
    log(`[chrome] 已选择浏览器：${chromePath}`)
  }

  const alreadyListening = await probeTcp(port)
  if (!alreadyListening) {
    try {
      if (isWin) {
        execSync('taskkill /F /IM chrome.exe /T', { timeout: 5000 })
      } else {
        execSync(`osascript -e 'quit app "Google Chrome"'`, { timeout: 5000 })
      }
      await new Promise(r => setTimeout(r, 2500))
    } catch (_) {}

    // Chrome v115+ 需要 --user-data-dir 才能开 CDP
    const os = require('os')
    const userDataDir = path.join(os.homedir(), '.temu-assistant', 'chrome-profile')
    fs.mkdirSync(userDataDir, { recursive: true })

    log(`[chrome] 启动 Chrome --remote-debugging-port=${port} --user-data-dir=${userDataDir}`)
    const chromeProc = spawn(chromePath, [
      `--remote-debugging-port=${port}`,
      `--user-data-dir=${userDataDir}`,
      '--no-first-run',
      '--no-default-browser-check',
      'https://agentseller.temu.com/',
    ], { detached: !isWin, stdio: 'ignore' })
    if (!isWin) chromeProc.unref()

    for (let i = 0; i < 50; i++) {
      await new Promise(r => setTimeout(r, 600))
      if (await probeTcp(port)) {
        sendStatus('chrome', true)
        return { ok: true, msg: `Chrome 已启动，CDP 端口 ${port}` }
      }
    }
    return { ok: false, msg: 'Chrome 已启动但 CDP 未响应，请手动确认' }
  } else {
    // Chrome 已运行（带 CDP）—— 确保 Temu 标签存在
    try {
      const http = require('http')
      const tabs = await new Promise((resolve) => {
        http.get(`http://127.0.0.1:${port}/json`, (res) => {
          let data = ''
          res.on('data', d => data += d)
          res.on('end', () => { try { resolve(JSON.parse(data)) } catch { resolve([]) } })
        }).on('error', () => resolve([]))
      })
      const hasTemu = tabs.some(t => t.type === 'page' && t.url && t.url.includes('temu.com'))
      if (!hasTemu) {
        const p2 = spawn(chromePath, ['https://agentseller.temu.com/'], { detached: !isWin, stdio: 'ignore' })
        if (!isWin) p2.unref()
        log('[chrome] 已在 Chrome 中打开 Temu 运营后台')
      }
    } catch (_) {}
    sendStatus('chrome', true)
    return { ok: true, msg: `Chrome CDP 已就绪（端口 ${port}）` }
  }
}

// ── Python subprocess (run-task) ──────────────────────────────────────────────
let runningProcess = null

function runPythonTask(scriptName, args) {
  return new Promise((resolve) => {
    if (runningProcess) {
      resolve({ ok: false, msg: '已有任务在运行，请先停止' })
      return
    }

    const pythonBin = getPythonBin()
    const scriptsDir = getPythonScriptsDir()
    const allArgs = [scriptName, ...args]

    log(`[run] ${pythonBin} ${allArgs.join(' ')}`)

    runningProcess = spawn(pythonBin, allArgs, {
      cwd: scriptsDir,
      stdio: ['ignore', 'pipe', 'pipe'],
      env: {
        ...process.env,
        PYTHONIOENCODING: 'utf-8',
        PYTHONUTF8: '1',
        ELECTRON_RESOURCES_PATH: isPkg() ? process.resourcesPath : '',
        ELECTRON_BB_BROWSER_SCRIPT: getBbDaemonScript(),
        ELECTRON_NODE_BIN: getNodeBin(),
        ELECTRON_NODE_NEEDS_FLAG: nodeNeedsElectronFlag() ? '1' : '',
      },
    })

    runningProcess.stdout.on('data', (d) => {
      d.toString('utf8').split('\n').filter(l => l.trim()).forEach(l => log(l))
    })
    runningProcess.stderr.on('data', (d) => {
      d.toString('utf8').split('\n').filter(l => l.trim()).forEach(l => log(`[err] ${l}`))
    })
    runningProcess.on('exit', (code) => {
      runningProcess = null
      sendStatus('running', false)
      resolve({ ok: code === 0, msg: `任务结束，exit code=${code}` })
    })
    runningProcess.on('error', (err) => {
      runningProcess = null
      sendStatus('running', false)
      resolve({ ok: false, msg: err.message })
    })

    sendStatus('running', true)
  })
}

// ── Config helpers ────────────────────────────────────────────────────────────
function getConfigPath() {
  return path.join(getPythonScriptsDir(), 'config.yaml')
}

function readConfig() {
  const yaml = require('js-yaml')
  try {
    const content = fs.readFileSync(getConfigPath(), 'utf8')
    return yaml.load(content) || {}
  } catch (_) {
    return {}
  }
}

function writeConfig(cfg) {
  const yaml = require('js-yaml')
  fs.writeFileSync(getConfigPath(), yaml.dump(cfg), 'utf8')
}

function loadChromePath() {
  try { return readConfig().chrome_path || '' } catch { return '' }
}

function saveChromePath(p) {
  try {
    const cfg = readConfig()
    cfg.chrome_path = p
    writeConfig(cfg)
  } catch (_) {}
}

// ── Logging helper ────────────────────────────────────────────────────────────
function log(msg) {
  const ts = new Date().toLocaleTimeString('zh-CN', { hour12: false })
  const line = `[${ts}] ${msg}`
  console.log(line)
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('log', line)
  }
}

function sendStatus(key, value) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('status', { key, value })
  }
}

// ── IPC handlers ──────────────────────────────────────────────────────────────

ipcMain.handle('get-status', async () => {
  const chromeOk = await probeTcp(CDP_PORT)
  return {
    chrome: chromeOk,
    daemon: daemonReady,
    running: !!runningProcess,
    configPath: getConfigPath(),
    pythonBin: getPythonBin(),
    scriptsDir: getPythonScriptsDir(),
    bbScript: getBbDaemonScript(),
  }
})

ipcMain.handle('launch-chrome', async (_, customPath) => {
  const saved = customPath || loadChromePath()
  return await launchChrome(CDP_PORT, saved)
})

ipcMain.handle('check-chrome', async () => {
  const ok = await checkChromeCdp()
  return { ok }
})

ipcMain.handle('get-chrome-path', async () => {
  return { path: loadChromePath() }
})

ipcMain.handle('save-chrome-path', async (_, p) => {
  saveChromePath(p)
  return { ok: true }
})

ipcMain.handle('browse-chrome-path', async () => {
  const isWin = process.platform === 'win32'
  const result = await dialog.showOpenDialog(mainWindow, {
    title: '选择 Chrome / Edge 可执行文件',
    buttonLabel: '选择',
    filters: isWin
      ? [{ name: 'Executable', extensions: ['exe'] }]
      : [{ name: 'Application', extensions: ['app', ''] }],
    properties: ['openFile'],
  })
  if (result.canceled || !result.filePaths.length) return { path: '' }
  return { path: result.filePaths[0] }
})

ipcMain.handle('get-config', async () => {
  return readConfig()
})

ipcMain.handle('save-config', async (_, cfg) => {
  try {
    writeConfig(cfg)
    return { ok: true }
  } catch (e) {
    return { ok: false, msg: e.message }
  }
})

// ensure-chrome: 检查 CDP，没开就自动启动
ipcMain.handle('ensure-chrome', async () => {
  const ok = await probeTcp(CDP_PORT)
  if (ok) return { ok: true, msg: 'Chrome CDP 已就绪' }

  log('[chrome] CDP 未就绪，自动启动 Chrome...')
  const saved = loadChromePath()
  const result = await launchChrome(CDP_PORT, saved)
  return result
})

// run-task: 接收 { task, params } 派发对应的 temu_*.py
ipcMain.handle('run-task', async (_, task, params) => {
  if (runningProcess) {
    return { ok: false, msg: '已有任务在运行，请先停止当前任务' }
  }

  // 自动确保 Chrome CDP 就绪
  const cdpOk = await probeTcp(CDP_PORT)
  if (!cdpOk) {
    log('[pre-task] CDP 未就绪，自动启动 Chrome...')
    sendStatus('chrome', false)
    const saved = loadChromePath()
    const r = await launchChrome(CDP_PORT, saved)
    if (!r.ok) {
      return { ok: false, msg: `Chrome 启动失败：${r.msg}\n请手动以 CDP 模式启动 Chrome 后重试` }
    }
    log('[pre-task] Chrome CDP 就绪，开始任务')
  }

  let scriptName = ''
  let args = []

  switch (task) {
    case 'goods-data': {
      scriptName = 'temu_goods_data.py'
      const mode = params.mode || 'current'
      args = ['--mode', mode]
      if (params.start_date) args.push('--start', params.start_date)
      if (params.end_date)   args.push('--end',   params.end_date)
      break
    }
    case 'aftersales': {
      scriptName = 'temu_aftersales.py'
      const mode = params.mode || 'current'
      args = ['--mode', mode]
      if (params.regions && params.regions.length) {
        args.push('--regions', ...params.regions)
      }
      break
    }
    case 'reviews': {
      scriptName = 'temu_reviews.py'
      if (!params.shop_url) return { ok: false, msg: '请提供店铺链接' }
      args = [params.shop_url]
      break
    }
    case 'store-items': {
      scriptName = 'temu_store_items.py'
      if (!params.shop_url) return { ok: false, msg: '请提供店铺链接' }
      args = [params.shop_url]
      break
    }
    default:
      return { ok: false, msg: `未知任务类型: ${task}` }
  }

  log(`[task] 启动任务: ${task}`)
  // 异步执行，不阻塞 IPC 返回
  runPythonTask(scriptName, args).then(r => {
    log(`[task] 任务结束: ${task} → ${r.msg}`)
  })

  return { ok: true, msg: `任务 ${task} 已启动` }
})

ipcMain.handle('stop-task', async () => {
  if (runningProcess) {
    runningProcess.kill('SIGTERM')
    runningProcess = null
    sendStatus('running', false)
    log('[task] 任务已停止')
    return { ok: true }
  }
  return { ok: false, msg: '没有正在运行的任务' }
})

ipcMain.handle('open-output-dir', async () => {
  const desktopPath = require('os').homedir() + '/Desktop'
  shell.openPath(desktopPath)
  return { ok: true }
})

ipcMain.handle('get-recent-files', async () => {
  const desktopPath = require('os').homedir() + '/Desktop'
  if (!fs.existsSync(desktopPath)) return []
  try {
    const files = fs.readdirSync(desktopPath)
      .filter(f => f.startsWith('temu_') && f.endsWith('.xlsx'))
      .map(f => {
        const fullPath = path.join(desktopPath, f)
        const stat = fs.statSync(fullPath)
        return {
          name: f,
          path: fullPath,
          mtime: stat.mtime,
          size: stat.size,
        }
      })
      .sort((a, b) => b.mtime - a.mtime)
      .slice(0, 10)
    return files
  } catch (_) {
    return []
  }
})

ipcMain.handle('open-file', async (_, filePath) => {
  shell.openPath(filePath)
  return { ok: true }
})

ipcMain.handle('show-in-finder', async (_, filePath) => {
  shell.showItemInFolder(filePath)
  return { ok: true }
})
