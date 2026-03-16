# =============================================================================
#  JD Price Monitor — 一键安装脚本（Windows PowerShell）
#  用法：右键 → 使用 PowerShell 运行
#  或终端：  Set-ExecutionPolicy Bypass -Scope Process; .\install.ps1
# =============================================================================

$ErrorActionPreference = "Stop"
$PROJ_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$VENV_DIR = Join-Path $PROJ_DIR "venv"
$ADAPTER_DIR = Join-Path $env:USERPROFILE ".bb-browser\bb-sites\jd"

function Write-Step   { param($n,$msg) Write-Host "`n" -NoNewline; Write-Host "[$n] " -ForegroundColor Cyan -NoNewline; Write-Host $msg }
function Write-Ok     { param($msg) Write-Host "  OK  $msg" -ForegroundColor Green }
function Write-Info   { param($msg) Write-Host "  ->  $msg" -ForegroundColor Cyan }
function Write-Warn   { param($msg) Write-Host "  !   $msg" -ForegroundColor Yellow }
function Write-Err    { param($msg) Write-Host "  X   $msg" -ForegroundColor Red }

Write-Host ""
Write-Host "  ╔══════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "  ║     JD Price Monitor — 安装程序          ║" -ForegroundColor Cyan
Write-Host "  ║     京东价格监控 · 一键安装 (Windows)    ║" -ForegroundColor Cyan
Write-Host "  ╚══════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# =============================================================================
# Step 1: 检查 Python 3.9+
# =============================================================================
Write-Step "1/5" "检查 Python 环境"

$PYTHON = $null
foreach ($cmd in @("python3.12","python3.11","python3.10","python3.9","python3","python")) {
    try {
        $ver = & $cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        $parts = $ver.Split(".")
        if ([int]$parts[0] -ge 3 -and [int]$parts[1] -ge 9) {
            $PYTHON = $cmd
            Write-Ok "Python $ver ($cmd)"
            break
        }
    } catch {}
}

if (-not $PYTHON) {
    Write-Err "未找到 Python 3.9+，请先安装："
    Write-Host "    https://www.python.org/downloads/"
    Write-Host "    安装时请勾选 'Add Python to PATH'"
    Read-Host "按 Enter 退出"
    exit 1
}

# =============================================================================
# Step 2: 创建虚拟环境 & 安装 Python 依赖
# =============================================================================
Write-Step "2/5" "安装 Python 依赖"

$VENV_PYTHON = Join-Path $VENV_DIR "Scripts\python.exe"
$VENV_PIP    = Join-Path $VENV_DIR "Scripts\pip.exe"

if (-not (Test-Path $VENV_PYTHON)) {
    Write-Info "创建虚拟环境 ..."
    & $PYTHON -m venv $VENV_DIR
}

Write-Info "升级 pip ..."
& $VENV_PIP install --upgrade pip -q

Write-Info "安装依赖（rich, questionary, openpyxl, pyyaml ...）..."
& $VENV_PIP install -r (Join-Path $PROJ_DIR "requirements.txt") -q
Write-Ok "Python 依赖安装完成"

# =============================================================================
# Step 3: 检查 Node.js & 安装 bb-browser
# =============================================================================
Write-Step "3/5" "安装 bb-browser"

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Err "未找到 Node.js，请先安装："
    Write-Host "    https://nodejs.org/  （推荐 LTS 版本）"
    Read-Host "按 Enter 退出"
    exit 1
}
$nodeVer = (node --version).TrimStart("v")
Write-Ok "Node.js $nodeVer"

Write-Info "安装 / 更新 bb-browser ..."
npm install -g bb-browser
Write-Ok "bb-browser 安装完成"

Write-Info "更新 bb-browser 社区 adapter 库 ..."
try { bb-browser site update 2>$null } catch { Write-Warn "adapter 更新失败（可忽略）" }

# =============================================================================
# Step 4: 安装 JD adapter
# =============================================================================
Write-Step "4/5" "安装 JD adapter"

if (-not (Test-Path $ADAPTER_DIR)) {
    New-Item -ItemType Directory -Path $ADAPTER_DIR -Force | Out-Null
}
Copy-Item -Path (Join-Path $PROJ_DIR "adapters\jd\shop-prices.js") `
          -Destination (Join-Path $ADAPTER_DIR "shop-prices.js") -Force
Write-Ok "adapter 已复制到 $ADAPTER_DIR\shop-prices.js"

# =============================================================================
# Step 5: 创建启动脚本
# =============================================================================
Write-Step "5/5" "创建启动脚本"

# 生成 jd-monitor.bat
$launcher_bat = Join-Path $PROJ_DIR "jd-monitor.bat"
@"
@echo off
"$VENV_PYTHON" "$PROJ_DIR\cli.py" %*
"@ | Set-Content -Path $launcher_bat -Encoding UTF8

# 生成桌面快捷方式（可选）
try {
    $WshShell   = New-Object -ComObject WScript.Shell
    $shortcut   = $WshShell.CreateShortcut("$env:USERPROFILE\Desktop\JD价格监控.lnk")
    $shortcut.TargetPath = $launcher_bat
    $shortcut.WorkingDirectory = $PROJ_DIR
    $shortcut.Description = "JD Price Monitor 京东价格监控"
    $shortcut.Save()
    Write-Ok "桌面快捷方式已创建：JD价格监控.lnk"
} catch {
    Write-Warn "桌面快捷方式创建失败（可忽略）"
}

Write-Ok "启动脚本：$launcher_bat"

# =============================================================================
# 完成
# =============================================================================
Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Green
Write-Host "  ✅ 安装完成！" -ForegroundColor Green
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Green
Write-Host ""
Write-Host "使用前，请完成以下准备：" -ForegroundColor White
Write-Host ""
Write-Host "  1. " -NoNewline; Write-Host "启动 bb-browser daemon（新开一个终端窗口运行）" -ForegroundColor Cyan
Write-Host "     node `"`$(npm root -g)/bb-browser/dist/daemon.js`""
Write-Host ""
Write-Host "  2. " -NoNewline; Write-Host "打开 Chrome 并启用远程调试" -ForegroundColor Cyan
Write-Host '     & "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222'
Write-Host ""
Write-Host "  3. " -NoNewline; Write-Host "安装 bb-browser Chrome 扩展（仅首次）" -ForegroundColor Cyan
Write-Host "     chrome://extensions/ → 开发者模式 → 加载已解压的扩展程序"
$npmRoot = (npm root -g).Trim()
Write-Host "     路径：$npmRoot\bb-browser\extension"
Write-Host ""
Write-Host "  4. " -NoNewline; Write-Host "在 Chrome 中打开京东并登录" -ForegroundColor Cyan
Write-Host ""
Write-Host "然后运行（或双击桌面快捷方式）：" -ForegroundColor White
Write-Host "     $launcher_bat" -ForegroundColor Green
Write-Host ""
Write-Host "提示：首次运行后，可在设置菜单中配置店铺 URL、阈值、钉钉 Webhook" -ForegroundColor Yellow
Write-Host ""
Read-Host "按 Enter 退出"
