'use strict'

// Unset ELECTRON_RUN_AS_NODE so that child processes we spawn (bb-browser daemon,
// Python) do not accidentally inherit this flag and run in Node-only mode.
delete process.env.ELECTRON_RUN_AS_NODE

const { app, BrowserWindow, ipcMain, shell, dialog } = require('electron')
const path = require('path')
const fs = require('fs')
const net = require('net')
const { spawn, execSync } = require('child_process')

// ── Path helpers ──────────────────────────────────────────────────────────────
// Note: app.isPackaged is evaluated lazily so it's available after app is ready
function isPkg() { return app.isPackaged }

function getPythonBin() {
  if (isPkg()) {
    // Windows: python/python.exe  |  macOS/Linux: python/bin/python3
    const winBin = path.join(process.resourcesPath, 'python', 'python.exe')
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
  // In development, use system node if available
  // In packaged app, use Electron binary with ELECTRON_RUN_AS_NODE=1
  if (!isPkg()) {
    // Try to find system node
    try {
      const which = require('child_process').execSync('which node', { encoding: 'utf8' }).trim()
      if (which) return which
    } catch (_) {}
    // Windows dev: try where node
    if (process.platform === 'win32') {
      try {
        const which = require('child_process').execSync('where node', { encoding: 'utf8' }).split('\n')[0].trim()
        if (which) return which
      } catch (_) {}
    }
  }
  return process.execPath  // Will be used with ELECTRON_RUN_AS_NODE=1
}

// 判断 getNodeBin() 返回的是否是 Electron 可执行文件（需要 ELECTRON_RUN_AS_NODE=1）
function nodeNeedsElectronFlag() {
  return getNodeBin() === process.execPath
}

function getDataDir() {
  const scriptsDir = getPythonScriptsDir()
  return path.join(scriptsDir, 'data')
}

// ── Window ────────────────────────────────────────────────────────────────────
let mainWindow = null

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1100,
    height: 720,
    minWidth: 900,
    minHeight: 600,
    titleBarStyle: 'hiddenInset',
    backgroundColor: '#0f1117',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'))

  // Open DevTools in dev mode
  if (!isPkg()) {
    mainWindow.webContents.openDevTools({ mode: 'detach' })
  }

  mainWindow.on('closed', () => { mainWindow = null })
}

// ── Adapter 安装 ──────────────────────────────────────────────────────────────
// bb-browser 的 `site` 命令只认 ~/.bb-browser/sites/ 目录。
// 打包后 adapters 在 resources/python-scripts/adapters/，需要在启动时 copy 过去。
function installAdapters() {
  try {
    const os = require('os')
    const bbSitesDir = path.join(os.homedir(), '.bb-browser', 'sites')
    fs.mkdirSync(bbSitesDir, { recursive: true })

    // 确定 adapters 源目录
    const adaptersSrc = isPkg()
      ? path.join(process.resourcesPath, 'python-scripts', 'adapters')
      : path.join(__dirname, '..', '..', 'adapters')

    if (!fs.existsSync(adaptersSrc)) {
      log(`⚠️  adapters 源目录不存在：${adaptersSrc}`)
      return
    }

    // 递归 copy adapters/ → ~/.bb-browser/sites/
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
    log(`✅ adapters 已安装到 ${bbSitesDir}`)
  } catch (e) {
    log(`⚠️  安装 adapters 失败：${e.message}`)
  }
}

app.whenReady().then(async () => {
  createWindow()
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })

  // 把内嵌 adapters 安装到 ~/.bb-browser/sites/（bb-browser site 命令依赖此目录）
  installAdapters()

  // 启动 Backend server（AI 助手 + FastAPI）
  await startBackend()

  // 自动启动 Chrome（调试模式）
  log('🚀 正在自动启动 Chrome 调试模式…')
  const chromeResult = await launchChrome()
  log(`Chrome: ${chromeResult.msg}`)

  // 标记 daemon 为就绪（bb-browser 直接 CLI 调用，无需 daemon server）
  daemonReady = true
  sendStatus('daemon', true)
  log('✅ bb-browser 已就绪（直接 CLI 模式）')
})

app.on('window-all-closed', () => {
  stopBbDaemon()
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
  // 如果已经在监听就跳过
  if (await probeTcp(BACKEND_PORT)) {
    log(`✅ Backend server 已在端口 ${BACKEND_PORT} 运行`)
    return
  }

  const pythonBin = getPythonBin()
  const serverScript = getBackendScript()

  if (!fs.existsSync(serverScript)) {
    log(`⚠️  Backend server 脚本未找到：${serverScript}`)
    return
  }

  log(`🚀 启动 Backend server: ${pythonBin} ${serverScript} ${BACKEND_PORT}`)
  backendProcess = spawn(pythonBin, [serverScript, String(BACKEND_PORT)], {
    cwd: getPythonScriptsDir(),
    stdio: ['ignore', 'pipe', 'pipe'],
    env: {
      ...process.env,
      PYTHONIOENCODING: 'utf-8',
      PYTHONUTF8: '1',
      // 告知 server.py 内嵌资源根路径，用于定位 python / python-scripts 等目录
      ELECTRON_RESOURCES_PATH: isPkg() ? process.resourcesPath : '',
      // bb-browser 内嵌路径，供 sku_fetcher.py 定位
      ELECTRON_BB_BROWSER_SCRIPT: getBbDaemonScript(),
      ELECTRON_NODE_BIN: getNodeBin(),
      // 若 node 是 Electron 可执行文件，Python 调用时需设置 ELECTRON_RUN_AS_NODE=1
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

  // 等待端口就绪（最多 10 秒）
  for (let i = 0; i < 20; i++) {
    await new Promise(r => setTimeout(r, 500))
    if (await probeTcp(BACKEND_PORT)) {
      log(`✅ Backend server 已就绪（端口 ${BACKEND_PORT}）`)
      return
    }
  }
  log(`⚠️  Backend server 启动超时，AI 助手功能可能不可用`)
}

function stopBackend() {
  if (backendProcess) {
    if (process.platform === 'win32') {
      // Windows: SIGTERM 不可靠，用 taskkill 强制终止整个进程树
      try {
        execSync(`taskkill /F /T /PID ${backendProcess.pid}`, { timeout: 3000 })
      } catch (_) {}
    } else {
      backendProcess.kill('SIGTERM')
    }
    backendProcess = null
  }
}

// ── bb-browser daemon ─────────────────────────────────────────────────────────
let bbDaemonProcess = null
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

async function waitForDaemon(port = 3399, retries = 30, interval = 500) {
  for (let i = 0; i < retries; i++) {
    if (await probeTcp(port)) return true
    await new Promise(r => setTimeout(r, interval))
  }
  return false
}

async function startBbDaemon() {
  if (daemonReady) return { ok: true, msg: 'Daemon already running' }

  // Check if already listening on port 3399
  if (await probeTcp(3399)) {
    daemonReady = true
    sendStatus('daemon', true)
    return { ok: true, msg: 'Daemon already running on port 3399' }
  }

  const nodeBin = getNodeBin()
  const daemonScript = getBbDaemonScript()

  if (!fs.existsSync(daemonScript)) {
    return { ok: false, msg: `bb-browser not found at: ${daemonScript}` }
  }

  log(`Starting bb-browser daemon: ${nodeBin} ${daemonScript} daemon`)

  // When using Electron binary as Node, set ELECTRON_RUN_AS_NODE=1
  const daemonEnv = { ...process.env }
  if (nodeBin === process.execPath) {
    daemonEnv.ELECTRON_RUN_AS_NODE = '1'
  }

  bbDaemonProcess = spawn(nodeBin, [daemonScript, 'daemon'], {
    stdio: ['ignore', 'pipe', 'pipe'],
    detached: false,
    env: daemonEnv,
  })

  bbDaemonProcess.stdout.on('data', (d) => log(`[bb-daemon] ${d.toString('utf8').trim()}`))
  bbDaemonProcess.stderr.on('data', (d) => log(`[bb-daemon] ${d.toString('utf8').trim()}`))
  bbDaemonProcess.on('exit', (code) => {
    log(`[bb-daemon] exited with code ${code}`)
    daemonReady = false
    sendStatus('daemon', false)
  })

  const ready = await waitForDaemon(3399)
  if (ready) {
    daemonReady = true
    sendStatus('daemon', true)
    return { ok: true, msg: 'Daemon started successfully' }
  } else {
    bbDaemonProcess.kill()
    bbDaemonProcess = null
    return { ok: false, msg: 'Daemon failed to start (port 3399 not responding)' }
  }
}

function stopBbDaemon() {
  if (bbDaemonProcess) {
    bbDaemonProcess.kill()
    bbDaemonProcess = null
    daemonReady = false
  }
}

// ── Chrome CDP management ─────────────────────────────────────────────────────
async function checkChromeCdp(port = 9222) {
  const ok = await probeTcp(port)
  sendStatus('chrome', ok)
  return ok
}

async function launchChrome(port = 9222, customPath = '') {
  const isWin = process.platform === 'win32'
  const CHROME_PATHS = isWin ? [
    // Windows 常见安装路径
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
    process.env.LOCALAPPDATA
      ? `${process.env.LOCALAPPDATA}\\Google\\Chrome\\Application\\chrome.exe`
      : '',
    process.env.PROGRAMFILES
      ? `${process.env.PROGRAMFILES}\\Google\\Chrome\\Application\\chrome.exe`
      : '',
    // Edge 作为备选
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
    'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
  ].filter(Boolean) : [
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
  ]

  // 优先用自定义路径
  let chromePath = null
  if (customPath && fs.existsSync(customPath)) {
    chromePath = customPath
  } else {
    for (const p of CHROME_PATHS) {
      if (fs.existsSync(p)) { chromePath = p; break }
    }
  }

  // 找不到 → 弹出文件选择对话框
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
    // 保存到配置，下次直接用
    saveChromePath(chromePath)
    log(`✅ 已选择浏览器：${chromePath}`)
  }

  // Check if Chrome is running WITHOUT CDP — if so, quit it first
  const alreadyListening = await probeTcp(port)
  if (!alreadyListening) {
    try {
      // Gracefully quit Chrome so we can re-launch with CDP flag
      if (isWin) {
        execSync('taskkill /F /IM chrome.exe /T', { timeout: 5000 })
      } else {
        execSync(`osascript -e 'quit app "Google Chrome"'`, { timeout: 5000 })
      }
      // 等待 Chrome 完全退出
      await new Promise(r => setTimeout(r, 2500))
    } catch (_) {
      // Chrome wasn't running — fine
    }

    log(`Launching Chrome with --remote-debugging-port=${port}`)
    const chromeProc = spawn(chromePath, [
      `--remote-debugging-port=${port}`,
      '--no-first-run',
      '--no-default-browser-check',
      'https://www.jd.com',
    ], { detached: !isWin, stdio: 'ignore' })
    if (!isWin) chromeProc.unref()

    // Wait for CDP to become available（最多等 30 秒）
    for (let i = 0; i < 50; i++) {
      await new Promise(r => setTimeout(r, 600))
      if (await probeTcp(port)) {
        sendStatus('chrome', true)
        return { ok: true, msg: `Chrome launched with CDP on port ${port}` }
      }
    }
    return { ok: false, msg: 'Chrome launched but CDP not responding — 请手动确认 Chrome 已打开，或在 Chrome 连接页面点击「刷新状态」' }
  } else {
    // Chrome already running with CDP — ensure JD tab exists
    try {
      const http = require('http')
      const tabs = await new Promise((resolve) => {
        http.get(`http://127.0.0.1:${port}/json`, (res) => {
          let data = ''
          res.on('data', d => data += d)
          res.on('end', () => { try { resolve(JSON.parse(data)) } catch { resolve([]) } })
        }).on('error', () => resolve([]))
      })
      const hasJd = tabs.some(t => t.type === 'page' && t.url && t.url.includes('jd.com'))
      if (!hasJd) {
        const p2 = spawn(chromePath, ['https://www.jd.com'], { detached: !isWin, stdio: 'ignore' })
        if (!isWin) p2.unref()
        log('已在 Chrome 中打开京东页面')
      }
    } catch (_) {}
    sendStatus('chrome', true)
    return { ok: true, msg: `Chrome CDP already available on port ${port}` }
  }
}

// ── Python subprocess ─────────────────────────────────────────────────────────
let runningProcess = null

function runPython(args) {
  return new Promise((resolve) => {
    if (runningProcess) {
      resolve({ ok: false, msg: 'Another process is already running' })
      return
    }

    const pythonBin = getPythonBin()
    const scriptsDir = getPythonScriptsDir()

    log(`Running: ${pythonBin} ${args.join(' ')}`)
    log(`CWD: ${scriptsDir}`)

    runningProcess = spawn(pythonBin, args, {
      cwd: scriptsDir,
      stdio: ['ignore', 'pipe', 'pipe'],
      env: {
        ...process.env,
        PYTHONIOENCODING: 'utf-8',
        PYTHONUTF8: '1',
        ELECTRON_RESOURCES_PATH: isPkg() ? process.resourcesPath : '',
        // bb-browser 内嵌路径，供 sku_fetcher.py 定位
        ELECTRON_BB_BROWSER_SCRIPT: getBbDaemonScript(),
        ELECTRON_NODE_BIN: getNodeBin(),
        // 若 node 是 Electron 可执行文件，Python 调用时需设置 ELECTRON_RUN_AS_NODE=1
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
      resolve({ ok: code === 0, msg: `Process exited with code ${code}` })
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
  } catch (e) {
    return {}
  }
}

function writeConfig(cfg) {
  const yaml = require('js-yaml')
  fs.writeFileSync(getConfigPath(), yaml.dump(cfg), 'utf8')
}

// Chrome 路径持久化（存在 config.yaml 的 chrome_path 字段）
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

// ── Loop task ─────────────────────────────────────────────────────────────────
let loopTimer = null

function stopLoop() {
  if (loopTimer) {
    clearTimeout(loopTimer)
    loopTimer = null
    log('⏹ 循环巡检已停止')
    sendStatus('looping', false)
  }
}

async function runLoop(intervalMinutes) {
  const ms = intervalMinutes * 60 * 1000
  const tick = async () => {
    if (!loopTimer) return  // stopped
    log(`\n🔄 循环巡检触发 (间隔 ${intervalMinutes} 分钟)`)
    await runPython(['main.py'])
    if (loopTimer) {
      loopTimer = setTimeout(tick, ms)
    }
  }
  loopTimer = setTimeout(tick, ms)
  sendStatus('looping', true)
  log(`⏰ 循环巡检已启动，每 ${intervalMinutes} 分钟执行一次`)
}

// ── IPC handlers ──────────────────────────────────────────────────────────────

ipcMain.handle('get-status', async () => {
  const chromeOk = await probeTcp(9222)
  const daemonOk = await probeTcp(3399)
  return {
    chrome: chromeOk,
    daemon: daemonOk || daemonReady,
    running: !!runningProcess,
    looping: !!loopTimer,
    configPath: getConfigPath(),
    dataDir: getDataDir(),
    pythonBin: getPythonBin(),
    scriptsDir: getPythonScriptsDir(),
    bbScript: getBbDaemonScript(),
  }
})

ipcMain.handle('start-daemon', async () => {
  return await startBbDaemon()
})

ipcMain.handle('launch-chrome', async (_, customPath) => {
  const saved = customPath || loadChromePath()
  return await launchChrome(9222, saved)
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

ipcMain.handle('check-chrome', async () => {
  const ok = await checkChromeCdp()
  return { ok }
})

ipcMain.handle('run-once', async () => {
  return await runPython(['main.py'])
})

ipcMain.handle('stop-run', async () => {
  if (runningProcess) {
    runningProcess.kill('SIGTERM')
    runningProcess = null
    sendStatus('running', false)
    log('⏹ 运行已中止')
    return { ok: true }
  }
  return { ok: false, msg: 'No process running' }
})

ipcMain.handle('start-loop', async (_, intervalMinutes) => {
  if (loopTimer) return { ok: false, msg: 'Already looping' }
  await runLoop(intervalMinutes || 60)
  return { ok: true }
})

ipcMain.handle('stop-loop', async () => {
  stopLoop()
  return { ok: true }
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

ipcMain.handle('open-data-dir', async () => {
  const dataDir = getDataDir()
  if (!fs.existsSync(dataDir)) {
    fs.mkdirSync(dataDir, { recursive: true })
  }
  shell.openPath(dataDir)
  return { ok: true }
})

ipcMain.handle('show-in-finder', async (_, filePath) => {
  shell.showItemInFolder(filePath)
  return { ok: true }
})

ipcMain.handle('get-recent-files', async () => {
  const dataDir = getDataDir()
  if (!fs.existsSync(dataDir)) return []
  const files = fs.readdirSync(dataDir)
    .filter(f => f.endsWith('.xlsx') || f.endsWith('.json'))
    .map(f => ({
      name: f,
      path: path.join(dataDir, f),
      mtime: fs.statSync(path.join(dataDir, f)).mtime,
    }))
    .sort((a, b) => b.mtime - a.mtime)
    .slice(0, 10)
  return files
})

ipcMain.handle('open-file', async (_, filePath) => {
  shell.openPath(filePath)
  return { ok: true }
})

// ── Cron task management ───────────────────────────────────────────────────────
function parseCrontab() {
  if (process.platform === 'win32') return []
  try {
    const out = require('child_process').execSync('crontab -l 2>/dev/null || true', { encoding: 'utf8' })
    const lines = out.split('\n').filter(l => l.trim() && !l.trim().startsWith('#'))
    return lines
  } catch (_) { return [] }
}

function writeCrontab(lines) {
  if (process.platform === 'win32') throw new Error('Windows 不支持 crontab')
  const content = lines.join('\n') + '\n'
  const tmpFile = path.join(require('os').tmpdir(), 'jd_cron_tmp')
  fs.writeFileSync(tmpFile, content)
  require('child_process').execSync(`crontab "${tmpFile}"`)
  fs.unlinkSync(tmpFile)
}

ipcMain.handle('cron-list', async () => {
  try {
    return { ok: true, lines: parseCrontab() }
  } catch (e) { return { ok: false, msg: e.message, lines: [] } }
})

ipcMain.handle('cron-add', async (_, entry) => {
  try {
    const lines = parseCrontab()
    lines.push(entry)
    writeCrontab(lines)
    return { ok: true }
  } catch (e) { return { ok: false, msg: e.message } }
})

ipcMain.handle('cron-delete', async (_, index) => {
  try {
    const lines = parseCrontab()
    if (index < 0 || index >= lines.length) return { ok: false, msg: '索引越界' }
    lines.splice(index, 1)
    writeCrontab(lines)
    return { ok: true }
  } catch (e) { return { ok: false, msg: e.message } }
})
