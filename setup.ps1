# =============================================================================
#  JD Price Monitor — 远程一键安装脚本（Windows PowerShell）
#
#  用法（直接粘贴到 PowerShell）：
#    irm https://raw.githubusercontent.com/howtimeschange/jd-price-monitor/main/setup.ps1 | iex
#
#  或指定安装目录：
#    $env:JD_INSTALL_DIR="C:\jd-price-monitor"; irm https://raw.githubusercontent.com/howtimeschange/jd-price-monitor/main/setup.ps1 | iex
# =============================================================================

$ErrorActionPreference = "Stop"
$REPO = "https://github.com/howtimeschange/jd-price-monitor.git"
$INSTALL_DIR = if ($env:JD_INSTALL_DIR) { $env:JD_INSTALL_DIR } else { Join-Path $env:USERPROFILE "jd-price-monitor" }

function Write-Ok   { param($m) Write-Host "  OK  $m" -ForegroundColor Green }
function Write-Info { param($m) Write-Host "  ->  $m" -ForegroundColor Cyan }
function Write-Warn { param($m) Write-Host "  !   $m" -ForegroundColor Yellow }
function Write-Err  { param($m) Write-Host "  X   $m" -ForegroundColor Red }

Write-Host ""
Write-Host "  ╔══════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "  ║     JD Price Monitor — 一键安装          ║" -ForegroundColor Cyan
Write-Host "  ║     京东价格监控 (Windows)               ║" -ForegroundColor Cyan
Write-Host "  ╚══════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# ── 检查 git ──────────────────────────────────────────────────────────────────
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Err "未找到 git，请先安装："
    Write-Host "    https://git-scm.com/download/win"
    Read-Host "按 Enter 退出"; exit 1
}

# ── 克隆 / 更新仓库 ───────────────────────────────────────────────────────────
Write-Info "安装目录：$INSTALL_DIR"

if (Test-Path (Join-Path $INSTALL_DIR ".git")) {
    Write-Info "目录已存在，更新到最新版本..."
    git -C $INSTALL_DIR pull --ff-only
    Write-Ok "已更新"
} elseif (Test-Path $INSTALL_DIR) {
    $items = Get-ChildItem $INSTALL_DIR -ErrorAction SilentlyContinue
    if ($items.Count -gt 0) {
        Write-Err "目录 $INSTALL_DIR 已存在且非空，请指定其他路径："
        Write-Host '    $env:JD_INSTALL_DIR="C:\other-dir"; irm ... | iex'
        Read-Host "按 Enter 退出"; exit 1
    }
    git clone --depth 1 $REPO $INSTALL_DIR
    Write-Ok "克隆完成"
} else {
    Write-Info "克隆仓库 ..."
    git clone --depth 1 $REPO $INSTALL_DIR
    Write-Ok "克隆完成"
}

# ── 运行 install.ps1 ──────────────────────────────────────────────────────────
Set-Location $INSTALL_DIR
& "$INSTALL_DIR\install.ps1"

# ── 最终提示 ──────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "项目已安装到：$INSTALL_DIR" -ForegroundColor Cyan
Write-Host ""
Write-Host "  进入目录：  cd $INSTALL_DIR"
Write-Host "  启动程序：  jd-monitor.bat" -ForegroundColor Green
Write-Host ""
