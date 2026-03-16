#!/usr/bin/env bash
# =============================================================================
#  JD Price Monitor — 一键安装脚本（macOS / Linux）
#  用法：bash install.sh
# =============================================================================
set -e

PROJ_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJ_DIR/venv"
ADAPTER_DIR="$HOME/.bb-browser/bb-sites/jd"

# ── 颜色输出 ─────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
ok()   { echo -e "${GREEN}  ✓  $*${RESET}"; }
info() { echo -e "${CYAN}  →  $*${RESET}"; }
warn() { echo -e "${YELLOW}  ⚠  $*${RESET}"; }
err()  { echo -e "${RED}  ✗  $*${RESET}"; }
step() { echo -e "\n${BOLD}[$1]${RESET} $2"; }

echo -e "${BOLD}"
echo "  ╔══════════════════════════════════════════╗"
echo "  ║     JD Price Monitor — 安装程序          ║"
echo "  ║     京东价格监控 · 一键安装              ║"
echo "  ╚══════════════════════════════════════════╝"
echo -e "${RESET}"

# =============================================================================
# Step 1: 检查 Python 3.9+
# =============================================================================
step "1/5" "检查 Python 环境"

PYTHON=""
for cmd in python3.12 python3.11 python3.10 python3.9 python3 python; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
        major=$(echo "$ver" | cut -d. -f1)
        minor=$(echo "$ver" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 9 ]; then
            PYTHON="$cmd"
            ok "Python $ver ($cmd)"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    err "未找到 Python 3.9+，请先安装："
    echo "    macOS:  brew install python3"
    echo "    Ubuntu: sudo apt install python3.11"
    exit 1
fi

# =============================================================================
# Step 2: 创建虚拟环境 & 安装 Python 依赖
# =============================================================================
step "2/5" "安装 Python 依赖"

if [ ! -d "$VENV_DIR" ]; then
    info "创建虚拟环境 $VENV_DIR ..."
    "$PYTHON" -m venv "$VENV_DIR"
fi

VENV_PYTHON="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

info "升级 pip ..."
"$VENV_PIP" install --upgrade pip -q

info "安装依赖（rich, questionary, openpyxl, pyyaml ...）..."
"$VENV_PIP" install -r "$PROJ_DIR/requirements.txt" -q
ok "Python 依赖安装完成"

# =============================================================================
# Step 3: 检查 Node.js & 安装 bb-browser
# =============================================================================
step "3/5" "安装 bb-browser"

if ! command -v node &>/dev/null; then
    err "未找到 Node.js（需要 18+），请先安装："
    echo "    macOS:  brew install node"
    echo "    Ubuntu: sudo apt install nodejs npm  （或用 nvm）"
    exit 1
fi

NODE_VER=$(node --version | tr -d 'v')
NODE_MAJOR=$(echo "$NODE_VER" | cut -d. -f1)
if [ "$NODE_MAJOR" -lt 18 ]; then
    warn "Node.js 版本 $NODE_VER 低于推荐的 18，可能出现兼容问题"
else
    ok "Node.js $NODE_VER"
fi

# 安装 bb-browser
if command -v bb-browser &>/dev/null; then
    CURRENT_VER=$(bb-browser --version 2>/dev/null || echo "0")
    LATEST_VER=$(npm show bb-browser version 2>/dev/null || echo "$CURRENT_VER")
    if [ "$CURRENT_VER" = "$LATEST_VER" ]; then
        ok "bb-browser $CURRENT_VER（已是最新）"
    else
        info "升级 bb-browser $CURRENT_VER → $LATEST_VER ..."
        npm install -g bb-browser -q
        ok "bb-browser 升级完成"
    fi
else
    info "安装 bb-browser ..."
    npm install -g bb-browser -q
    ok "bb-browser 安装完成"
fi

# 更新社区 adapter 库
info "更新 bb-browser 社区 adapter 库 ..."
bb-browser site update 2>/dev/null || warn "adapter 更新失败（可忽略，将使用本地 adapter）"

# =============================================================================
# Step 4: 安装 JD 价格 adapter
# =============================================================================
step "4/5" "安装 JD adapter"

mkdir -p "$ADAPTER_DIR"
cp "$PROJ_DIR/adapters/jd/shop-prices.js" "$ADAPTER_DIR/shop-prices.js"
cp "$PROJ_DIR/adapters/jd/item-price.js"  "$ADAPTER_DIR/item-price.js"
ok "adapter 已复制到 $ADAPTER_DIR/"

# =============================================================================
# Step 5: 创建启动脚本
# =============================================================================
step "5/5" "创建启动脚本"

# 创建 jd-monitor 快捷启动脚本
LAUNCHER="$PROJ_DIR/jd-monitor"
cat > "$LAUNCHER" <<EOF
#!/usr/bin/env bash
# JD Price Monitor 启动脚本
PROJ_DIR="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
"\$PROJ_DIR/venv/bin/python" "\$PROJ_DIR/cli.py" "\$@"
EOF
chmod +x "$LAUNCHER"
ok "启动脚本：$LAUNCHER"

# 可选：在 ~/bin 里建软链（如果目录存在且在 PATH 中）
if [ -d "$HOME/bin" ] && echo "$PATH" | grep -q "$HOME/bin"; then
    ln -sf "$LAUNCHER" "$HOME/bin/jd-monitor" 2>/dev/null && \
        ok "软链已创建：~/bin/jd-monitor（可全局使用 jd-monitor 命令）"
fi

# =============================================================================
# 完成
# =============================================================================
echo ""
echo -e "${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${GREEN}${BOLD}  ✅ 安装完成！${RESET}"
echo -e "${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo ""
echo -e "${BOLD}使用前，请完成以下准备：${RESET}"
echo ""
echo -e "  ${CYAN}1. 启动 bb-browser daemon${RESET}"
echo -e "     node \$(npm root -g)/bb-browser/dist/daemon.js"
echo ""
echo -e "  ${CYAN}2. 打开 Chrome 并启用远程调试${RESET}"
echo -e "     open -a 'Google Chrome' --args --remote-debugging-port=9222"
echo ""
echo -e "  ${CYAN}3. 安装 bb-browser Chrome 扩展（仅首次）${RESET}"
echo -e "     chrome://extensions/ → 开发者模式 → 加载已解压的扩展程序"
echo -e "     路径：\$(npm root -g)/bb-browser/extension"
echo ""
echo -e "  ${CYAN}4. 在 Chrome 中打开京东并登录${RESET}"
echo ""
echo -e "${BOLD}然后运行：${RESET}"
echo ""
echo -e "     ${GREEN}${BOLD}./jd-monitor${RESET}   （或：${GREEN}venv/bin/python cli.py${RESET}）"
echo ""
echo -e "${YELLOW}  提示：首次运行后，可在设置菜单中配置店铺 URL、阈值、钉钉 Webhook${RESET}"
echo ""
