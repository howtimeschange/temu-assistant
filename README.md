# JD Price Monitor（京东价格监控）

> 监控京东自营店铺所有 SKU 的前台价格，自动发现破价商品，通过钉钉推送告警。

> **🖥️ macOS + Windows 桌面客户端已上线** — 图形界面管理所有功能，内置 AI 助手，告别命令行。[跳转查看 →](#️-macos--windows-桌面客户端)

## 一键安装

> **前置条件：** Python 3.9+、Node.js 18+、Git、Chrome 浏览器

**macOS / Linux** — 打开终端，粘贴一条命令：

```bash
curl -fsSL https://raw.githubusercontent.com/howtimeschange/jd-price-monitor/main/setup.sh | bash
```

**Windows** — 打开 PowerShell，粘贴一条命令：

```powershell
irm https://raw.githubusercontent.com/howtimeschange/jd-price-monitor/main/setup.ps1 | iex
```

脚本会自动完成：克隆仓库 → 创建 Python 虚拟环境 → 安装所有依赖 → 安装 bb-browser → 部署 JD adapter → 生成启动脚本。

<details>
<summary>已有仓库 / 手动安装</summary>

```bash
# macOS / Linux
git clone https://github.com/howtimeschange/jd-price-monitor.git
cd jd-price-monitor
bash install.sh

# Windows PowerShell
git clone https://github.com/howtimeschange/jd-price-monitor.git
cd jd-price-monitor
Set-ExecutionPolicy Bypass -Scope Process; .\install.ps1
```

</details>

## 技术方案

本项目使用 **[bb-browser](https://github.com/epiral/bb-browser)** 方案抓取价格，完全绕过京东反爬检测：

- bb-browser 在用户**真实 Chrome 浏览器**内执行 JS，使用浏览器本身的 Cookie 和网络
- 不需要任何 API Key，不会被风控拦截
- 价格通过滚动触发懒加载，100% 准确
- 对列表页仍无价格的 SKU，自动访问**商品详情页兜底补全**，确保价格尽量完整

## 安装后的一次性配置

安装完成后，首次使用前需要完成以下步骤（之后无需重复）：

**1. 启动 bb-browser daemon**（新开一个终端窗口，保持运行）
```bash
# macOS / Linux
node $(npm root -g)/bb-browser/dist/daemon.js

# Windows PowerShell
node "$((npm root -g).Trim())\bb-browser\dist\daemon.js"
```

**2. 以远程调试模式打开 Chrome**
```bash
# macOS
open -a "Google Chrome" --args --remote-debugging-port=9222

# Windows
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222
```

**3. 安装 bb-browser Chrome 扩展**（仅首次）
1. 打开 `chrome://extensions/` → 开启"开发者模式"
2. 点击"加载已解压的扩展程序"
3. 路径（macOS/Linux）：`$(npm root -g)/bb-browser/extension`
4. 路径（Windows）：运行 `npm root -g` 查看，再拼上 `\bb-browser\extension`

**4. 在 Chrome 中打开京东并登录**

## 启动

```bash
# macOS / Linux
./jd-monitor

# Windows
jd-monitor.bat   # 或双击桌面快捷方式（安装时自动创建）
```

启动后显示交互式主菜单：

```
  JD Price Monitor  京东价格监控系统

  当前配置
  店铺      ASICS亚瑟士京东自营旗舰店
  阈值      50折  (50%)
  巡检间隔  120 分钟
  Webhook   ✅ 已配置

  请选择操作：
  > 📦  导出全店商品价格  →  Excel
    🔍  立即执行一次破价巡检
    🔁  循环巡检（按间隔自动运行）
    ⏰  定时任务管理
    ⚙️   设置  —  店铺 / 阈值 / Webhook / 导出设置
    ❌  退出
```

## 功能详解

### 📦 导出全店商品价格 → Excel

逐页抓取店铺全部商品，导出到 Excel（默认保存到桌面）。

**价格兜底逻辑**：列表页抓取后，对仍然缺失价格的 SKU 自动访问商品详情页补全，确保覆盖率最大化。

Excel 颜色标记：
- 普通行：白/浅蓝交替
- **淡黄行**：由详情页兜底补全（`price_source = detail_page`）
- **淡红行**：兜底后仍无价格
- 末尾含统计摘要（总计 / 有价格 / 兜底补全 / 仍缺失）

新增"价格来源"列，方便排查数据质量。

### 🔍 立即执行一次破价巡检

单次抓取全店价格，与吊牌价对比，超阈值立即通过钉钉告警。

### 🔁 循环巡检

按配置间隔（默认 2 小时）持续巡检，支持：
- 前台运行（Ctrl+C 停止）
- 后台进程（日志写入 `logs/loop.log`）
- 可选每轮巡检后**自动导出 Excel 到桌面**

### ⏰ 定时任务管理

可视化管理 crontab 定时任务：
- 显示当前已有的本项目任务（表格：编号 / cron 表达式 / 命令摘要）
- 新增任务（自动生成表达式，或自定义 5 段 cron）
- 删除任务（按编号选择）

### ⚙️ 设置

- 店铺 URL / 名称（自动解析 shop_id）
- 破价阈值（如输入 `50` 即 5 折）
- 钉钉 Webhook（支持加签 + 一键测试）
- 巡检间隔
- Excel 输出位置（桌面 / data 目录）
- 循环巡检是否自动导出 Excel
- 首次启动登录等待时长（默认 30 秒）

**设置菜单**支持配置后立即生效，无需重启。

---

## 配置文件

`config.yaml` 全部选项：

```yaml
shop:
  shop_id: "1000462158"
  shop_url: "https://mall.jd.com/index-1000462158.html"
  shop_name: "ASICS亚瑟士京东自营旗舰店"

monitor:
  interval_minutes: 120        # 巡检间隔（分钟）
  price_ratio_threshold: 0.50  # 破价阈值（前台价 / 吊牌价）
  concurrency: 3
  page_timeout_seconds: 30
  delay_min_seconds: 1
  delay_max_seconds: 3

dingtalk:
  webhook_url: "https://oapi.dingtalk.com/robot/send?access_token=YOUR_TOKEN"
  secret: ""        # 加签密钥（可选）
  at_mobiles: []
  at_all: false

output:
  data_dir: "data"
  log_dir: "logs"
  keep_days: 30
  excel_to_desktop: true      # 导出 Excel 到桌面
  loop_export_excel: false    # 循环巡检时自动导出 Excel

startup:
  login_wait_seconds: 30      # 首次启动等待登录的秒数
```

---

## 项目结构

```
jd-price-monitor/
├── setup.sh / setup.ps1          # 远程一键安装入口
├── install.sh / install.bat / install.ps1  # 本地安装脚本
├── cli.py                        # ✨ 交互式 CLI 入口
├── main.py                       # 巡检核心逻辑（可独立运行）
├── loop_worker.py                # 后台循环巡检 worker
├── scrape_list.py                # 价格导出核心逻辑（可独立运行）
├── config.yaml                   # 主配置文件
├── requirements.txt              # Python 依赖（含 fastapi/uvicorn/httpx）
├── crontab.example               # 定时任务示例
├── adapters/
│   └── jd/
│       ├── shop-prices.js        # bb-browser 列表页 adapter
│       └── item-price.js         # bb-browser 详情页 adapter（兜底）
├── src/
│   ├── config.py                 # 配置加载 & 保存
│   ├── checker.py                # 破价检测逻辑
│   ├── dingtalk.py               # 钉钉告警
│   ├── excel_writer.py           # Excel 导出（含兜底标记高亮）
│   ├── sku_fetcher.py            # SKU + 价格抓取（含兜底补全）
│   ├── storage.py                # 历史记录存储
│   └── ai_agent.py               # 🤖 AI 助手 Agent（MiniMax M2.1 + 工具调用）
└── electron-app/                 # 🖥️ 桌面客户端
    ├── src/
    │   ├── main.js               # Electron 主进程（IPC / Chrome / backend 启动）
    │   ├── preload.js            # 安全 IPC 桥接
    │   └── renderer/             # 浮窗 UI（HTML + CSS + JS）
    ├── backend/
    │   └── server.py             # FastAPI 后端（AI 助手 / WebSocket 日志 / 配置 API）
    ├── assets/icon.icns          # App 图标
    ├── electron-builder.yml      # 打包配置
    └── scripts/                  # Python 内嵌下载 / 构建脚本
```

---

## 🖥️ macOS + Windows 桌面客户端

基于 Electron 构建的原生桌面 App，深色主题，侧边栏导航，实时日志流，无需配置终端环境。

### ⬇️ 直接下载

前往 **[Releases 页面](https://github.com/howtimeschange/jd-price-monitor/releases/latest)** 下载最新版本：

| 平台 | 文件 | 说明 |
|------|------|------|
| macOS（Apple Silicon）| `JD.Price.Monitor-*-arm64.dmg` | M1/M2/M3/M4 芯片 |
| macOS（Intel）| `JD.Price.Monitor-*-x64.dmg` | Intel 芯片 |
| Windows 10/11 | `JD-Price-Monitor-Setup-*.exe` | x64 安装程序（NSIS） |

> **⚠️ macOS 提示「已损坏，无法打开」？**
>
> 由于 App 未经 Apple 公证，macOS 会阻止首次运行。**两种方法任选其一：**
>
> **方法一（推荐）：** 打开 DMG 后，双击里面的 **「🔧 首次打开必读 - 修复已损坏.command」** 脚本，自动修复并启动。
> 如果脚本本身也提示无法打开，在终端运行：
> ```bash
> xattr -cr ~/Downloads/"🔧 首次打开必读 - 修复已损坏.command" && open ~/Downloads/"🔧 首次打开必读 - 修复已损坏.command"
> ```
>
> **方法二（手动）：** 将 App 拖入「应用程序」后，在终端运行：
> ```bash
> xattr -cr "/Applications/JD Price Monitor.app"
> ```
> 然后正常双击打开即可。

### 开发模式运行

```bash
cd electron-app
npm install
npm start
```

### 本地打包

```bash
cd electron-app
npm run bundle-python   # 下载内嵌 Python（首次需要）
npm run build:mac       # macOS DMG（arm64 + x64）
npm run build:win       # Windows NSIS installer
```

### 功能模块

**巡检运行** — 一键立即巡检 / 循环巡检，自定义间隔分钟数，实时日志流，进度状态显示。

**店铺设置** — 图形化配置店铺 ID / 名称 / Vendor ID / CDP 端口。

**巡检配置** — 破价阈值 / 循环间隔 / 历史保留天数，以及：
- 🕐 登录等待：首次启动预留 N 秒供用户登录京东（默认 30 秒）
- 🗂️ Excel 导出到桌面：开关控制，开启后结果直接出现在桌面
- 🔁 循环每轮导出 Excel：每次循环巡检完自动生成一份 Excel

**钉钉通知** — Webhook / Secret 图形化配置，一键开关。

**Chrome 连接** — 实时显示 Chrome CDP 和 bb-browser daemon 状态，一键启动 Chrome（自动注入 `--remote-debugging-port=9222`）。支持自定义浏览器路径：若自动检测失败，可手动填写或通过文件选择框定位 `chrome.exe`，路径持久化保存。

**AI 助手** — 内置基于 MiniMax M2.1 的智能助手，支持：
- 🔍 读取最近运行日志，自动排查抓取失败原因
- 📊 分析最新巡检结果，汇总破价 SKU
- ⚙️ 读取并修改 `config.yaml` 配置（钉钉 Webhook、巡检间隔、价格阈值等）
- 💬 响应式气泡布局，流式输出，支持文字选中复制
- 快捷提示词一键发送常用问题

**定时任务** — 基于系统 crontab 的可视化管理：
- 查看所有已有定时任务，支持单条删除
- 快速预设：每天 9:00 / 9&18点 / 工作日 9:00 / 每 2 小时
- 自定义 cron 表达式 + 备注，生成命令自动含 `--no-login-wait`

**数据文件** — 浏览最近生成的 Excel / JSON，直接打开或在 Finder 中定位。

### 技术架构

- Electron 主进程启动时自动拉起 FastAPI 后端（`backend/server.py`，端口 7788），提供 AI 助手、WebSocket 日志推送、配置读写等 API
- Python 子进程调用现有爬取逻辑，所有新功能（兜底补价、Excel 颜色高亮、价格来源列）一并生效
- 配置读写直接操作项目根目录的 `config.yaml`，与 CLI 版完全共用
- Windows 下 Chrome 路径自动检测（`Program Files`、`%LOCALAPPDATA%`、Edge 备选），找不到时弹出文件选择框

---

## 命令行直接运行（无 CLI）

```bash
# 导出价格 Excel
venv/bin/python scrape_list.py        # macOS/Linux
venv\Scripts\python scrape_list.py   # Windows

# 单次巡检（跳过登录等待）
venv/bin/python main.py --no-login-wait

# 循环巡检
venv/bin/python main.py --loop --no-login-wait
```

---

## 工作原理

```
cli.py / scrape_list.py
│
├── bb-browser tab list          # 找到 mall.jd.com tab
├── bb-browser eval navigate     # 切换到目标页，等待 25s
└── bb-browser site jd/shop-prices   # 在浏览器内执行列表页 adapter
    │
    ├── 等待价格元素渲染（最多 5s）
    ├── 分段滚动（10 步）触发懒加载价格
    ├── 读取 DOM：SKU ID / 名称 / 价格 / 链接
    ├── XHR 补查 p.3.cn（针对仍为空的价格）
    └── 返回 JSON + nextUrl（下一页链接）
        │
        └── [仍缺价格] bb-browser site jd/item-price   # 详情页兜底
            ├── 导航到 item.jd.com/{skuId}.html
            ├── 多选择器等待价格渲染（最多 8s）
            └── 读取 .p-price .price / del 等元素
```

## 告警示例

破价时钉钉会收到：

```
⚠️ 破价预警 | ASICS亚瑟士京东自营旗舰店
监控阈值：吊牌价 50折
本次发现 2 个 SKU 疑似破价

ASICS亚瑟士男款跑步鞋GEL-KAYANO...
- SKU: 100012043978
- 吊牌价: ¥1299.00 → 前台价: ¥599.00 (46.1%)
- 商品链接
```

## 注意事项

- bb-browser daemon 和 Chrome 必须保持运行，程序才能工作
- 吊牌价来源于商品列表页的划线价；若京东未展示划线价，该 SKU 跳过破价检测
- 建议在 Mac 不休眠状态下运行，或部署到 Windows Server / Linux VPS（需要有图形界面支持 Chrome）
- `cookies.json` 已加入 `.gitignore`，不会被提交
- nvm 安装的 Node.js 环境无需手动配置 PATH，程序会自动查找 bb-browser 可执行路径

## License

MIT

---

## Changelog

### v1.1.5 (2026-03-18)

- 🐛 **Windows 修复**：Electron 启动时自动将内嵌 adapter 安装到 `~/.bb-browser/sites/`，修复打包版 `bb-browser site jd/shop-prices` 找不到 adapter 导致抓取 0 个 SKU 的问题

### v1.1.4 (2026-03-18)

- 🔧 **CI 修复**：macOS x64 构建时用子 shell 执行 `npm install`，避免 `cd` 影响后续路径；bb-browser 依赖打包修复

### v1.1.3 (2026-03-17)

- 🔧 **打包修复**：CI 中为 bb-browser 安装独立 `node_modules`，修复打包后依赖缺失导致运行报错

### v1.1.2 (2026-03-17)

- 🐛 **Windows bb-browser 路径修复**：打包版正确解析 bb-browser 可执行路径
- 🤖 **AI 模型升级**：升级至 MiniMax M2.5，修复打包版 AI 模块路径推导和 JSON 解析错误
- 🍎 **macOS 修复**：DMG 内 `.command` 脚本自动清除 quarantine 属性，修复脚本本身被 Gatekeeper 拦截的问题

### v1.1.1 (2026-03-17)

- 🐛 **打包版关键修复**：修复 AI 后端依赖缺失、backend 未打包、Chrome CDP 连接等待超时等问题
- 🔧 多轮 code review 后的稳定性改进

### v1.1.0 (2026-03-17)

- 🤖 **AI 助手**：内置 MiniMax M2.1 智能助手，支持日志排查、巡检结果分析、配置修改，流式输出 + 工具调用
- 🖥️ **AI 面板 UI 重构**：响应式气泡布局，Key 输入框移至标题栏，欢迎占位卡片，流式光标动画
- 🪟 **Windows Chrome 兼容**：自动检测 `Program Files`、`%LOCALAPPDATA%`、Edge 等路径；找不到时弹出文件选择框；自定义路径持久化到 `config.yaml`
- 📋 **文字可复制**：运行日志、AI 回复、表单内容均支持鼠标选中复制
- 🔧 **Backend 自动启动**：Electron 启动时自动拉起 FastAPI 后端（端口 7788），开发模式优先使用项目 venv

### v1.0.0

- 初始发布：Electron 桌面客户端（macOS + Windows）
- 巡检运行 / 店铺设置 / 破价配置 / 钉钉通知 / Chrome 连接 / 定时任务 / 数据文件管理
