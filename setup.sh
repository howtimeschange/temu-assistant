#!/usr/bin/env bash
# =============================================================================
#  JD Price Monitor — 远程一键安装脚本（macOS / Linux）
#
#  用法（直接粘贴到终端）：
#    curl -fsSL https://raw.githubusercontent.com/howtimeschange/jd-price-monitor/main/setup.sh | bash
#
#  或指定安装目录：
#    curl -fsSL https://raw.githubusercontent.com/howtimeschange/jd-price-monitor/main/setup.sh | bash -s -- ~/my-dir
# =============================================================================
set -e

REPO="https://github.com/howtimeschange/jd-price-monitor.git"
INSTALL_DIR="${1:-$HOME/jd-price-monitor}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
ok()   { echo -e "${GREEN}  ✓  $*${RESET}"; }
info() { echo -e "${CYAN}  →  $*${RESET}"; }
warn() { echo -e "${YELLOW}  ⚠  $*${RESET}"; }
err()  { echo -e "${RED}  ✗  $*${RESET}"; }

echo -e "${BOLD}"
echo "  ╔══════════════════════════════════════════╗"
echo "  ║     JD Price Monitor — 一键安装          ║"
echo "  ║     京东价格监控                         ║"
echo "  ╚══════════════════════════════════════════╝"
echo -e "${RESET}"

# ── 检查 git ──────────────────────────────────────────────────────────────────
if ! command -v git &>/dev/null; then
    err "未找到 git，请先安装："
    echo "    macOS:  xcode-select --install  或  brew install git"
    echo "    Ubuntu: sudo apt install git"
    exit 1
fi

# ── 克隆仓库 ──────────────────────────────────────────────────────────────────
info "安装目录：$INSTALL_DIR"

if [ -d "$INSTALL_DIR/.git" ]; then
    info "目录已存在，更新到最新版本..."
    git -C "$INSTALL_DIR" pull --ff-only
    ok "已更新"
else
    if [ -d "$INSTALL_DIR" ] && [ "$(ls -A "$INSTALL_DIR" 2>/dev/null)" ]; then
        err "目录 $INSTALL_DIR 已存在且非空，请指定其他路径或手动清理"
        echo "    用法：curl ... | bash -s -- ~/other-dir"
        exit 1
    fi
    info "克隆仓库 ..."
    git clone --depth 1 "$REPO" "$INSTALL_DIR"
    ok "克隆完成"
fi

# ── 运行安装脚本 ──────────────────────────────────────────────────────────────
cd "$INSTALL_DIR"
bash install.sh

# ── 最终提示（覆盖 install.sh 末尾提示，补充 cd 路径）─────────────────────────
echo ""
echo -e "${BOLD}项目已安装到：${CYAN}$INSTALL_DIR${RESET}"
echo ""
echo -e "  进入目录：  ${BOLD}cd $INSTALL_DIR${RESET}"
echo -e "  启动程序：  ${GREEN}${BOLD}./jd-monitor${RESET}"
echo ""
