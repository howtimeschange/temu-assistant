'use strict'
/* global api */

// ── State ─────────────────────────────────────────────────────────────────────
const state = {
  running: false,
  runningTask: '',  // 当前运行的任务 id
  chromeOk: false,
  daemonOk: false,
}

// ── Log per-panel ─────────────────────────────────────────────────────────────
// 每个 panel 有自己的日志区域，同时也写入当前活跃 panel
const LOG_AREAS = {
  'goods':      document.getElementById('goods-log'),
  'aftersales': document.getElementById('aftersales-log'),
  'reviews':    document.getElementById('reviews-log'),
  'store':      document.getElementById('store-log'),
}

const MAX_LOG_LINES = 500

function appendLog(panelKey, msg, level = 'info') {
  const area = LOG_AREAS[panelKey]
  if (!area) return

  const line = document.createElement('div')
  line.className = `log-line log-${level}`
  line.textContent = msg

  area.appendChild(line)

  // 限制行数
  while (area.children.length > MAX_LOG_LINES) {
    area.removeChild(area.firstChild)
  }

  // 自动滚动到底部
  const atBottom = area.scrollHeight - area.clientHeight - area.scrollTop < 60
  if (atBottom) area.scrollTop = area.scrollHeight
}

function appendLogAll(msg, level = 'info') {
  for (const key of Object.keys(LOG_AREAS)) {
    appendLog(key, msg, level)
  }
}

// ── Indicators ────────────────────────────────────────────────────────────────
const $indChrome = document.getElementById('ind-chrome')
const $indDaemon = document.getElementById('ind-daemon')

function setIndicator(el, ok) {
  el.classList.toggle('connected', ok)
  el.classList.toggle('error', !ok)
}

// ── Navigation ────────────────────────────────────────────────────────────────
document.querySelectorAll('.nav-item').forEach(btn => {
  btn.addEventListener('click', async () => {
    document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'))
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'))
    btn.classList.add('active')
    const panelId = btn.dataset.panel
    document.getElementById(panelId).classList.add('active')
    if (panelId === 'panel-files') refreshFiles()
    if (panelId === 'panel-settings') {
      refreshChromeStatus()
      const r = await api.getChromePath()
      if (r.path) document.getElementById('chrome-custom-path').value = r.path
    }
  })
})

// ── IPC: events from main ─────────────────────────────────────────────────────
api.onLog(msg => {
  // 写入当前运行任务的 log 区，或者写入所有面板
  const taskPanelMap = {
    'goods-data':   'goods',
    'aftersales':   'aftersales',
    'reviews':      'reviews',
    'store-items':  'store',
  }
  const panelKey = taskPanelMap[state.runningTask] || null

  // 解析日志级别
  let level = 'info'
  const lower = msg.toLowerCase()
  if (lower.includes('[err]') || lower.includes('error') || lower.includes('❌')) level = 'error'
  else if (lower.includes('warn') || lower.includes('⚠')) level = 'warn'

  if (panelKey) {
    appendLog(panelKey, msg, level)
  } else {
    appendLogAll(msg, level)
  }
})

api.onStatus(({ key, value }) => {
  if (key === 'chrome') {
    state.chromeOk = value
    setIndicator($indChrome, value)
    updateChromeCard()
  }
  if (key === 'daemon') {
    state.daemonOk = value
    setIndicator($indDaemon, value)
  }
  if (key === 'running') {
    state.running = value
    if (!value) {
      // 任务结束 → 恢复所有按钮
      onTaskFinished()
    }
  }
})

// ── Init ──────────────────────────────────────────────────────────────────────
async function init() {
  const status = await api.getStatus()
  state.chromeOk = status.chrome
  state.daemonOk = status.daemon
  state.running = status.running

  setIndicator($indChrome, status.chrome)
  setIndicator($indDaemon, status.daemon)

  appendLogAll(`[系统] Temu 运营助手已启动`)
  appendLogAll(`[系统] Python: ${status.pythonBin}`)
  appendLogAll(`[系统] 脚本目录: ${status.scriptsDir}`)
}

init()

// ── Task helpers ──────────────────────────────────────────────────────────────
function setTaskRunning(taskId, panelKey) {
  state.running = true
  state.runningTask = taskId

  // 显示 badge
  const badge = document.getElementById(`${panelKey}-status-badge`)
  if (badge) badge.classList.remove('hidden')

  // 切换按钮
  const startBtn = document.getElementById(`btn-${panelKey}-start`)
  const stopBtn  = document.getElementById(`btn-${panelKey}-stop`)
  if (startBtn) startBtn.classList.add('hidden')
  if (stopBtn)  stopBtn.classList.remove('hidden')
}

function onTaskFinished() {
  const taskPanelMap = {
    'goods-data':   'goods',
    'aftersales':   'aftersales',
    'reviews':      'reviews',
    'store-items':  'store',
  }
  const panelKey = taskPanelMap[state.runningTask] || null
  state.running = false
  state.runningTask = ''

  if (panelKey) {
    const badge = document.getElementById(`${panelKey}-status-badge`)
    if (badge) badge.classList.add('hidden')
    const startBtn = document.getElementById(`btn-${panelKey}-start`)
    const stopBtn  = document.getElementById(`btn-${panelKey}-stop`)
    if (startBtn) startBtn.classList.remove('hidden')
    if (stopBtn)  stopBtn.classList.add('hidden')
  }
}

async function stopCurrentTask() {
  const r = await api.stopTask()
  if (r.ok) {
    showToast('任务已停止')
    onTaskFinished()
  }
}

// ── 商品数据 ──────────────────────────────────────────────────────────────────
// 时间区间联动：选「自定义」时显示日期输入行
document.getElementById('goods-time-range').addEventListener('change', function () {
  const customRow = document.getElementById('goods-custom-date-row')
  if (this.value === '自定义') {
    customRow.style.display = ''
    // 默认填入近7日的日期范围
    const today = new Date()
    const end = today.toISOString().slice(0, 10)
    const start = new Date(today - 6 * 86400000).toISOString().slice(0, 10)
    if (!document.getElementById('goods-start-date').value) document.getElementById('goods-start-date').value = start
    if (!document.getElementById('goods-end-date').value) document.getElementById('goods-end-date').value = end
  } else {
    customRow.style.display = 'none'
  }
})

document.getElementById('btn-goods-start').addEventListener('click', async () => {
  if (state.running) { showToast('请先停止当前任务'); return }

  const mode = document.querySelector('input[name="goods-mode"]:checked')?.value || 'current'
  const timeRange = document.getElementById('goods-time-range').value
  const params = { mode }
  if (timeRange) params.time_range = timeRange
  if (timeRange === '自定义') {
    params.start_date = document.getElementById('goods-start-date').value
    params.end_date = document.getElementById('goods-end-date').value
    if (!params.start_date || !params.end_date) {
      showToast('请填写自定义日期范围')
      return
    }
  }

  appendLog('goods', '\n▶ 开始抓取商品数据…')
  setTaskRunning('goods-data', 'goods')
  const r = await api.runTask('goods-data', params)
  if (!r.ok) {
    appendLog('goods', `❌ ${r.msg}`, 'error')
    onTaskFinished()
  }
})

document.getElementById('btn-goods-stop').addEventListener('click', stopCurrentTask)
document.getElementById('btn-clear-goods-log').addEventListener('click', () => {
  document.getElementById('goods-log').innerHTML = ''
})

// ── 售后数据 ──────────────────────────────────────────────────────────────────
document.getElementById('btn-aftersales-start').addEventListener('click', async () => {
  if (state.running) { showToast('请先停止当前任务'); return }

  const mode = document.querySelector('input[name="aftersales-mode"]:checked')?.value || 'current'
  const regions = Array.from(
    document.querySelectorAll('input[name="aftersales-region"]:checked')
  ).map(el => el.value)

  const params = { mode, regions }

  appendLog('aftersales', '\n▶ 开始抓取售后数据…')
  setTaskRunning('aftersales', 'aftersales')
  const r = await api.runTask('aftersales', params)
  if (!r.ok) {
    appendLog('aftersales', `❌ ${r.msg}`, 'error')
    onTaskFinished()
  }
})

document.getElementById('btn-aftersales-stop').addEventListener('click', stopCurrentTask)
document.getElementById('btn-clear-aftersales-log').addEventListener('click', () => {
  document.getElementById('aftersales-log').innerHTML = ''
})

// ── 店铺评价 ──────────────────────────────────────────────────────────────────
document.getElementById('btn-reviews-start').addEventListener('click', async () => {
  if (state.running) { showToast('请先停止当前任务'); return }

  const shopUrl = document.getElementById('reviews-url').value.trim()
  if (!shopUrl) { showToast('请填写店铺链接'); return }

  appendLog('reviews', '\n▶ 开始抓取店铺评价…')
  setTaskRunning('reviews', 'reviews')
  const r = await api.runTask('reviews', { shop_url: shopUrl })
  if (!r.ok) {
    appendLog('reviews', `❌ ${r.msg}`, 'error')
    onTaskFinished()
  }
})

document.getElementById('btn-reviews-stop').addEventListener('click', stopCurrentTask)
document.getElementById('btn-clear-reviews-log').addEventListener('click', () => {
  document.getElementById('reviews-log').innerHTML = ''
})

// ── 站点商品 ──────────────────────────────────────────────────────────────────
document.getElementById('btn-store-start').addEventListener('click', async () => {
  if (state.running) { showToast('请先停止当前任务'); return }

  const shopUrl = document.getElementById('store-url').value.trim()
  if (!shopUrl) { showToast('请填写店铺链接'); return }

  appendLog('store', '\n▶ 开始抓取站点商品…')
  setTaskRunning('store-items', 'store')
  const r = await api.runTask('store-items', { shop_url: shopUrl })
  if (!r.ok) {
    appendLog('store', `❌ ${r.msg}`, 'error')
    onTaskFinished()
  }
})

document.getElementById('btn-store-stop').addEventListener('click', stopCurrentTask)
document.getElementById('btn-clear-store-log').addEventListener('click', () => {
  document.getElementById('store-log').innerHTML = ''
})

// ── 输出文件 ──────────────────────────────────────────────────────────────────
async function refreshFiles() {
  const files = await api.getRecentFiles()
  const container = document.getElementById('file-list')
  if (!files.length) {
    container.innerHTML = '<div class="empty-state">暂无 temu_*.xlsx 文件（文件生成在桌面）</div>'
    return
  }
  container.innerHTML = files.map(f => {
    const mtime = new Date(f.mtime).toLocaleString('zh-CN')
    const size = f.size ? `${(f.size / 1024).toFixed(1)} KB` : ''
    const safePath = f.path.replace(/\\/g, '\\\\').replace(/'/g, "\\'")
    return `
      <div class="file-item">
        <div class="file-item-left">
          <span class="file-name">${escapeHtml(f.name)}</span>
          <span class="file-meta">${mtime}${size ? ' · ' + size : ''}</span>
        </div>
        <div class="file-actions">
          <button class="btn btn-secondary btn-sm"
            onclick="api.openFile('${safePath}')">打开</button>
          <button class="btn btn-secondary btn-sm"
            onclick="api.showInFinder('${safePath}')">在 Finder 中显示</button>
        </div>
      </div>
    `
  }).join('')
}

document.getElementById('btn-refresh-files').addEventListener('click', refreshFiles)
document.getElementById('btn-open-desktop').addEventListener('click', () => api.openOutputDir())

// ── 设置 panel ────────────────────────────────────────────────────────────────
function updateChromeCard() {
  const card = document.getElementById('chrome-status-card')
  const text = document.getElementById('chrome-status-text')
  if (!card || !text) return
  card.classList.toggle('connected', state.chromeOk)
  card.classList.toggle('error', !state.chromeOk)
  text.textContent = state.chromeOk ? '✓ 已连接 (CDP :9222)' : '✗ 未连接'
}

async function refreshChromeStatus() {
  const status = await api.getStatus()
  state.chromeOk = status.chrome
  setIndicator($indChrome, status.chrome)
  updateChromeCard()
}

document.getElementById('btn-launch-chrome').addEventListener('click', async () => {
  const btn = document.getElementById('btn-launch-chrome')
  if (btn.disabled) return
  btn.disabled = true
  btn.textContent = '启动中…'
  const customPath = document.getElementById('chrome-custom-path').value.trim()
  appendLogAll('[chrome] 正在启动 Chrome (CDP)…')
  const r = await api.launchChrome(customPath || undefined)
  appendLogAll(`[chrome] ${r.msg}`)
  await refreshChromeStatus()
  showToast(r.ok ? '✅ Chrome 已启动，请在 Chrome 中登录 Temu 账号' : `❌ 启动失败: ${r.msg}`)
  btn.disabled = false
  btn.textContent = '启动 Chrome (CDP模式)'
})

document.getElementById('btn-check-chrome').addEventListener('click', async () => {
  const r = await api.checkChrome()
  showToast(r.ok ? 'Chrome CDP 连接正常' : 'Chrome CDP 未连接')
  await refreshChromeStatus()
})

document.getElementById('btn-browse-chrome').addEventListener('click', async () => {
  const r = await api.browseChromePath()
  if (r.path) document.getElementById('chrome-custom-path').value = r.path
})

document.getElementById('btn-save-chrome-path').addEventListener('click', async () => {
  const p = document.getElementById('chrome-custom-path').value.trim()
  await api.saveChromePath(p)
  showToast(p ? 'Chrome 路径已保存' : 'Chrome 路径已清空（恢复自动检测）')
})

// ── Utils ─────────────────────────────────────────────────────────────────────
function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function showToast(msg, durationMs = 2500) {
  const container = document.getElementById('toast-container')
  const toast = document.createElement('div')
  toast.className = 'toast'
  toast.textContent = msg
  container.appendChild(toast)
  requestAnimationFrame(() => toast.classList.add('toast-show'))
  setTimeout(() => {
    toast.classList.remove('toast-show')
    setTimeout(() => toast.remove(), 300)
  }, durationMs)
}
