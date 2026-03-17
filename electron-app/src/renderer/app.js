'use strict'
/* global api */

// ── State ─────────────────────────────────────────────────────────────────────
const state = {
  running: false,
  looping: false,
  daemonOk: false,
  chromeOk: false,
}

// ── DOM refs ──────────────────────────────────────────────────────────────────
const $logArea      = document.getElementById('log-area')
const $runStatus    = document.getElementById('run-status-text')
const $progressTrack = document.getElementById('progress-track')
const $btnRunOnce   = document.getElementById('btn-run-once')
const $btnStopRun   = document.getElementById('btn-stop-run')
const $btnStartLoop = document.getElementById('btn-start-loop')
const $btnStopLoop  = document.getElementById('btn-stop-loop')
const $loopInterval = document.getElementById('loop-interval')
const $indDaemon    = document.getElementById('ind-daemon')
const $indChrome    = document.getElementById('ind-chrome')

// ── Navigation ────────────────────────────────────────────────────────────────
document.querySelectorAll('.nav-item').forEach(btn => {
  btn.addEventListener('click', async () => {
    document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'))
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'))
    btn.classList.add('active')
    const panelId = btn.dataset.panel
    document.getElementById(panelId).classList.add('active')
    if (panelId === 'panel-files') refreshFiles()
    if (panelId === 'panel-cron') refreshCron()
    if (panelId === 'panel-chrome') {
      refreshChromeStatus()
      const r = await api.getChromePath()
      if (r.path) document.getElementById('chrome-custom-path').value = r.path
    }
  })
})

// ── Log ───────────────────────────────────────────────────────────────────────
function appendLog(msg) {
  const atBottom = $logArea.scrollHeight - $logArea.clientHeight - $logArea.scrollTop < 40
  $logArea.textContent += msg + '\n'
  if (atBottom) $logArea.scrollTop = $logArea.scrollHeight
}

document.getElementById('btn-clear-log').addEventListener('click', () => {
  $logArea.textContent = ''
})

// ── Status helpers ────────────────────────────────────────────────────────────
function setIndicator(el, ok) {
  el.classList.toggle('connected', ok)
  el.classList.toggle('error', !ok)
}

function applyStatus(s) {
  state.running = s.running
  state.looping = s.looping
  state.daemonOk = s.daemon
  state.chromeOk = s.chrome

  document.body.classList.toggle('running', s.running)
  document.body.classList.toggle('looping', s.looping)

  setIndicator($indDaemon, s.daemon)
  setIndicator($indChrome, s.chrome)

  $runStatus.textContent = s.running ? '🔄 运行中…' : (s.looping ? '⏰ 循环等待中' : '就绪')
  if (s.running) {
    $progressTrack.classList.remove('hidden')
  } else {
    $progressTrack.classList.add('hidden')
  }

  // 停止按钮：运行时 enabled，否则 disabled
  document.getElementById('btn-stop-run').disabled  = !s.running
  document.getElementById('btn-stop-loop').disabled = !s.looping
  // kill-bar 显隐
  const killBar = document.getElementById('kill-bar')
  if (killBar) killBar.classList.toggle('hidden', !s.running && !s.looping)
}

// ── IPC events ────────────────────────────────────────────────────────────────
api.onLog(msg => appendLog(msg))
api.onStatus(({ key, value }) => {
  if (key === 'daemon') {
    state.daemonOk = value
    setIndicator($indDaemon, value)
    updateChromePanel()
  }
  if (key === 'chrome') {
    state.chromeOk = value
    setIndicator($indChrome, value)
    updateChromePanel()
  }
  if (key === 'running') {
    state.running = value
    document.body.classList.toggle('running', value)
    $runStatus.textContent = value ? '🔄 运行中…' : '就绪'
    $progressTrack.classList.toggle('hidden', !value)
    document.getElementById('btn-stop-run').disabled = !value
    const killBar = document.getElementById('kill-bar')
    if (killBar) killBar.classList.toggle('hidden', !value && !state.looping)
  }
  if (key === 'looping') {
    state.looping = value
    document.body.classList.toggle('looping', value)
    document.getElementById('btn-stop-loop').disabled = !value
    const killBar = document.getElementById('kill-bar')
    if (killBar) killBar.classList.toggle('hidden', !state.running && !value)
  }
})

// ── Init ──────────────────────────────────────────────────────────────────────
async function init() {
  const status = await api.getStatus()
  applyStatus(status)
  await loadConfig()
  appendLog(`[系统] JD Price Monitor 已启动`)
  appendLog(`[系统] Python: ${status.pythonBin}`)
  appendLog(`[系统] 脚本目录: ${status.scriptsDir}`)
}

init()

// ── Run once ──────────────────────────────────────────────────────────────────
$btnRunOnce.addEventListener('click', async () => {
  if (state.running) return
  appendLog('\n▶ 开始立即巡检…')
  const r = await api.runOnce()
  appendLog(`\n${r.ok ? '✅' : '❌'} 巡检${r.ok ? '完成' : '失败'}`)
})

$btnStopRun.addEventListener('click', async () => {
  await api.stopRun()
})

// ── Loop ──────────────────────────────────────────────────────────────────────
$btnStartLoop.addEventListener('click', async () => {
  const interval = parseInt($loopInterval.value, 10) || 60
  appendLog(`\n⏰ 启动循环巡检，间隔 ${interval} 分钟…`)
  const r = await api.startLoop(interval)
  if (!r.ok) appendLog(`❌ ${r.msg}`)
})

$btnStopLoop.addEventListener('click', async () => {
  await api.stopLoop()
})

// ── Kill All ──────────────────────────────────────────────────────────────────
document.getElementById('btn-kill-all')?.addEventListener('click', async () => {
  if (!confirm('确认强制终止所有正在运行的任务？')) return
  if (state.running)  await api.stopRun()
  if (state.looping)  await api.stopLoop()
  showToast('🛑 已终止全部任务')
})

// ── Data dir button ───────────────────────────────────────────────────────────
document.getElementById('btn-open-data').addEventListener('click', () => {
  api.openDataDir()
})

// ── Config ────────────────────────────────────────────────────────────────────
async function loadConfig() {
  const cfg = await api.getConfig()
  const shop = cfg.shop || {}
  const check = cfg.check || {}
  const notify = cfg.dingtalk || {}

  document.getElementById('cfg-shop-name').value = shop.shop_name || ''
  document.getElementById('cfg-shop-id').value   = shop.shop_id   || ''
  document.getElementById('cfg-vendor-id').value = shop.vendor_id || ''
  document.getElementById('cfg-cdp-port').value  = cfg.cdp_port   || 9222

  document.getElementById('cfg-threshold').value  = check.threshold  || ''
  document.getElementById('cfg-interval').value   = check.interval   || ''
  document.getElementById('cfg-keep-days').value  = check.keep_days  || ''

  const startup = cfg.startup || {}
  const output  = cfg.output  || {}
  document.getElementById('cfg-login-wait').value      = startup.login_wait_seconds ?? 30
  document.getElementById('cfg-excel-to-desktop').checked   = output.excel_to_desktop  ?? true
  document.getElementById('cfg-loop-export-excel').checked  = output.loop_export_excel ?? false

  document.getElementById('cfg-dd-webhook').value = notify.webhook || ''
  document.getElementById('cfg-dd-secret').value  = notify.secret  || ''
  document.getElementById('cfg-dd-enabled').checked = notify.enabled || false
}

async function saveSection(sectionKey) {
  const cfg = await api.getConfig()
  let updated = { ...cfg }

  if (sectionKey === 'shop') {
    updated.shop = {
      shop_name: document.getElementById('cfg-shop-name').value.trim(),
      shop_id:   document.getElementById('cfg-shop-id').value.trim(),
      vendor_id: document.getElementById('cfg-vendor-id').value.trim(),
    }
    updated.cdp_port = parseInt(document.getElementById('cfg-cdp-port').value, 10) || 9222
  }

  if (sectionKey === 'check') {
    updated.check = {
      threshold: parseFloat(document.getElementById('cfg-threshold').value) || 5,
      interval:  parseInt(document.getElementById('cfg-interval').value, 10) || 60,
      keep_days: parseInt(document.getElementById('cfg-keep-days').value, 10) || 7,
    }
    updated.startup = {
      ...(cfg.startup || {}),
      login_wait_seconds: parseInt(document.getElementById('cfg-login-wait').value, 10) ?? 30,
    }
    updated.output = {
      ...(cfg.output || {}),
      excel_to_desktop:  document.getElementById('cfg-excel-to-desktop').checked,
      loop_export_excel: document.getElementById('cfg-loop-export-excel').checked,
    }
  }

  if (sectionKey === 'notify') {
    updated.dingtalk = {
      webhook: document.getElementById('cfg-dd-webhook').value.trim(),
      secret:  document.getElementById('cfg-dd-secret').value.trim(),
      enabled: document.getElementById('cfg-dd-enabled').checked,
    }
  }

  const r = await api.saveConfig(updated)
  if (r.ok) {
    showToast('✅ 已保存')
    appendLog(`[配置] ${sectionKey} 配置已保存`)
  } else {
    showToast(`❌ 保存失败: ${r.msg}`)
  }
}

document.getElementById('btn-save-shop').addEventListener('click', () => saveSection('shop'))
document.getElementById('btn-save-check').addEventListener('click', () => saveSection('check'))
document.getElementById('btn-save-notify').addEventListener('click', () => saveSection('notify'))

// ── Chrome panel ──────────────────────────────────────────────────────────────
function updateChromePanel() {
  const chromeDot  = document.getElementById('chrome-dot')
  const chromeText = document.getElementById('chrome-status-text')
  const daemonDot  = document.getElementById('daemon-dot')
  const daemonText = document.getElementById('daemon-status-text')

  const chromeCard = document.getElementById('chrome-status-card')
  const daemonCard = document.getElementById('daemon-status-card')

  chromeCard.classList.toggle('connected', state.chromeOk)
  chromeCard.classList.toggle('error', !state.chromeOk)
  chromeText.textContent = state.chromeOk ? '✓ 已连接 (CDP :9222)' : '✗ 未连接'

  daemonCard.classList.toggle('connected', state.daemonOk)
  daemonCard.classList.toggle('error', !state.daemonOk)
  daemonText.textContent = state.daemonOk ? '✓ 运行中 (:3399)' : '✗ 未运行'
}

async function refreshChromeStatus() {
  const status = await api.getStatus()
  state.chromeOk = status.chrome
  state.daemonOk = status.daemon
  setIndicator($indDaemon, status.daemon)
  setIndicator($indChrome, status.chrome)
  updateChromePanel()
}

document.getElementById('btn-launch-chrome').addEventListener('click', async () => {
  appendLog('[Chrome] 正在启动 Chrome (CDP)…')
  const customPath = document.getElementById('chrome-custom-path').value.trim()
  const r = await api.launchChrome(customPath || undefined)
  appendLog(`[Chrome] ${r.msg}`)
  await refreshChromeStatus()
})

document.getElementById('btn-check-chrome').addEventListener('click', refreshChromeStatus)

document.getElementById('btn-start-daemon').addEventListener('click', async () => {
  appendLog('[Daemon] 正在启动 bb-browser daemon…')
  const r = await api.startDaemon()
  appendLog(`[Daemon] ${r.msg}`)
  await refreshChromeStatus()
})

// 自定义 Chrome 路径
document.getElementById('btn-browse-chrome').addEventListener('click', async () => {
  const r = await api.browseChromePath()
  if (r.path) document.getElementById('chrome-custom-path').value = r.path
})

document.getElementById('btn-save-chrome-path').addEventListener('click', async () => {
  const p = document.getElementById('chrome-custom-path').value.trim()
  await api.saveChromePath(p)
  appendLog(`[Chrome] 自定义路径已保存：${p || '（已清空，恢复自动检测）'}`)
})

// ── Files panel ───────────────────────────────────────────────────────────────
async function refreshFiles() {
  const files = await api.getRecentFiles()
  const container = document.getElementById('file-list')
  if (!files.length) {
    container.innerHTML = '<div class="empty-state">暂无数据文件</div>'
    return
  }
  container.innerHTML = files.map(f => {
    const mtime = new Date(f.mtime).toLocaleString('zh-CN')
    return `
      <div class="file-item">
        <div class="file-item-left">
          <span class="file-name">${f.name}</span>
          <span class="file-meta">${mtime}</span>
        </div>
        <div class="file-actions">
          <button class="btn btn-secondary" style="padding:4px 10px;font-size:12px"
            onclick="api.openFile('${f.path.replace(/'/g, "\\'")}')">打开</button>
          <button class="btn btn-secondary" style="padding:4px 10px;font-size:12px"
            onclick="api.showInFinder('${f.path.replace(/'/g, "\\'")}')">在Finder中显示</button>
        </div>
      </div>
    `
  }).join('')
}

document.getElementById('btn-refresh-files').addEventListener('click', refreshFiles)

// ── Cron panel ────────────────────────────────────────────────────────────────
let _cronLines = []

async function refreshCron() {
  const r = await api.cronList()
  _cronLines = r.lines || []
  renderCronList(_cronLines)
}

function renderCronList(lines) {
  const container = document.getElementById('cron-list')
  if (!lines.length) {
    container.innerHTML = '<div class="empty-state">暂无定时任务</div>'
    return
  }
  container.innerHTML = lines.map((line, i) => `
    <div class="cron-item">
      <code class="cron-expr-display">${escapeHtml(line)}</code>
      <button class="btn btn-danger" style="padding:3px 10px;font-size:12px" onclick="deleteCron(${i})">删除</button>
    </div>
  `).join('')
}

function escapeHtml(str) {
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')
}

window.deleteCron = async function(index) {
  if (!confirm(`确认删除第 ${index + 1} 条任务？`)) return
  const r = await api.cronDelete(index)
  if (r.ok) {
    showToast('✅ 任务已删除')
    await refreshCron()
  } else {
    showToast(`❌ ${r.msg}`)
  }
}

document.getElementById('btn-refresh-cron').addEventListener('click', refreshCron)

document.getElementById('btn-cron-add').addEventListener('click', async () => {
  const expr    = document.getElementById('cron-expr').value.trim()
  const comment = document.getElementById('cron-comment').value.trim()
  if (!expr) { showToast('⚠️ 请输入 cron 表达式'); return }

  // 拼装命令行，自动找 python 路径（同 main.js 逻辑：从 status.pythonBin 取）
  const status = await api.getStatus()
  const pyBin  = status.pythonBin || 'python3'
  const dir    = status.scriptsDir || ''
  const cmd    = `${expr}  cd "${dir}" && ${pyBin} main.py --no-login-wait${comment ? '  # ' + comment : ''}`

  const r = await api.cronAdd(cmd)
  if (r.ok) {
    showToast('✅ 任务已添加')
    document.getElementById('cron-expr').value = ''
    document.getElementById('cron-comment').value = ''
    await refreshCron()
  } else {
    showToast(`❌ ${r.msg}`)
  }
})

// 快捷预设按钮
document.querySelectorAll('.btn-chip').forEach(btn => {
  btn.addEventListener('click', () => {
    document.getElementById('cron-expr').value = btn.dataset.expr
  })
})

// ── Toast ─────────────────────────────────────────────────────────────────────
function showToast(msg, durationMs = 2500) {
  let toast = document.getElementById('__toast')
  if (!toast) {
    toast = document.createElement('div')
    toast.id = '__toast'
    Object.assign(toast.style, {
      position: 'fixed', bottom: '24px', left: '50%',
      transform: 'translateX(-50%)',
      background: '#1e2535', border: '1px solid #2a3347',
      color: '#e2e8f0', padding: '8px 20px',
      borderRadius: '6px', fontSize: '13px',
      zIndex: '9999', pointerEvents: 'none',
      transition: 'opacity 0.2s',
    })
    document.body.appendChild(toast)
  }
  toast.textContent = msg
  toast.style.opacity = '1'
  clearTimeout(toast._timer)
  toast._timer = setTimeout(() => { toast.style.opacity = '0' }, durationMs)
}

// ── AI 助手 ────────────────────────────────────────────────────────────────
const aiMessages = document.getElementById('ai-messages')
const aiInput = document.getElementById('ai-input')
const btnAiSend = document.getElementById('btn-ai-send')
const btnAiSaveKey = document.getElementById('btn-ai-save-key')
const aiApiKeyInput = document.getElementById('ai-api-key')

let aiHistory = []
let aiApiKey = localStorage.getItem('ai_api_key') || ''
if (aiApiKey) aiApiKeyInput.value = '••••••••'

// 保存 API Key
btnAiSaveKey.addEventListener('click', async () => {
  const key = aiApiKeyInput.value.trim()
  if (!key || key === '••••••••') return
  aiApiKey = key
  localStorage.setItem('ai_api_key', key)
  await fetch('http://127.0.0.1:7788/api/ai/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ api_key: key }),
  })
  aiApiKeyInput.value = '••••••••'
  showToast('API Key 已保存')
})

// 快捷提示词
document.querySelectorAll('#panel-ai .btn-chip').forEach(btn => {
  btn.addEventListener('click', () => {
    aiInput.value = btn.dataset.prompt
    aiInput.focus()
  })
})

function appendAiMsg(role, content, streaming = false) {
  // 清除欢迎占位
  const welcome = aiMessages.querySelector('.ai-welcome')
  if (welcome) welcome.remove()

  const div = document.createElement('div')
  div.className = `ai-msg ai-msg-${role === 'user' ? 'user' : 'bot'}`
  if (streaming) div.id = 'ai-streaming'

  if (role === 'user') {
    div.innerHTML = `<div class="ai-bubble">${content.replace(/\n/g, '<br>')}</div>`
  } else {
    div.innerHTML = `<div class="ai-label">🤖 助手</div><div class="ai-bubble"><span class="ai-content">${content}</span></div>`
  }
  aiMessages.appendChild(div)
  aiMessages.scrollTop = aiMessages.scrollHeight
  return div
}

function renderMarkdown(text) {
  // 简单 markdown：代码块、加粗、换行
  return text
    .replace(/```([\s\S]*?)```/g, '<pre style="background:#0d1117;padding:8px;border-radius:4px;overflow-x:auto;font-size:12px">$1</pre>')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/\n/g, '<br>')
}

async function sendAiMessage(text) {
  if (!text.trim()) return
  if (!aiApiKey) {
    showToast('请先填写 MiniMax API Key')
    document.getElementById('panel-ai').querySelector('#ai-api-key').focus()
    return
  }

  appendAiMsg('user', text)
  aiHistory.push({ role: 'user', content: text })
  aiInput.value = ''
  btnAiSend.disabled = true

  const streamDiv = appendAiMsg('assistant', '', true)
  const contentSpan = streamDiv.querySelector('.ai-content')
  let fullText = ''

  try {
    const resp = await fetch('http://127.0.0.1:7788/api/ai/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages: aiHistory, api_key: aiApiKey }),
    })

    if (!resp.ok) {
      const err = await resp.json()
      contentSpan.innerHTML = `❌ ${err.error || '请求失败'}`
      btnAiSend.disabled = false
      return
    }

    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop()
      for (const line of lines) {
        if (!line.startsWith('data:')) continue
        const data = line.slice(5).trim()
        if (data === '[DONE]') break
        try {
          const obj = JSON.parse(data)
          if (obj.text) {
            fullText += obj.text
            contentSpan.innerHTML = renderMarkdown(fullText)
            aiMessages.scrollTop = aiMessages.scrollHeight
          }
        } catch (_) {}
      }
    }

    aiHistory.push({ role: 'assistant', content: fullText })
  } catch (e) {
    contentSpan.innerHTML = `❌ 连接失败：${e.message}`
  }

  streamDiv.removeAttribute('id')
  btnAiSend.disabled = false
}

btnAiSend.addEventListener('click', () => sendAiMessage(aiInput.value))
aiInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) sendAiMessage(aiInput.value)
})

// 初始化时同步已保存的 key 到后端
if (aiApiKey) {
  fetch('http://127.0.0.1:7788/api/ai/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ api_key: aiApiKey }),
  }).catch(() => {})
}
