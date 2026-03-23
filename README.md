# Temu 运营助手

<p align="center">
  <img src="electron-app/assets/icon.png" width="120" alt="Temu 运营助手" />
</p>

<p align="center">
  <strong>一键导出 Temu 运营数据到 Excel</strong><br/>
  商品数据 · 售后数据 · 店铺评价 · 店铺商品
</p>

<p align="center">
  <img src="https://img.shields.io/badge/platform-macOS%20%7C%20Windows-lightgrey" />
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" />
  <img src="https://img.shields.io/badge/license-MIT-green" />
</p>

---

## ✨ 功能

| 模块 | 说明 |
|------|------|
| 📦 商品数据 | 抓取 agentseller 后台商品销售数据，支持昨日 / 近7日 / 近30日 / 自定义日期范围 |
| 🔄 售后数据 | 抓取全球/美国/欧区售后工单，多地区分 Sheet 输出 |
| ⭐ 店铺评价 | 按店铺链接抓取全量评价（用户、星级、内容、规格、图片） |
| 🛍️ 店铺商品 | 抓取店铺全量商品列表（名称、价格、销量、链接） |

所有结果自动保存到**桌面** `temu_*.xlsx`，表头加粗冻结、列宽自适应。

---

## 🚀 快速开始

### 下载安装（推荐）

前往 [Releases](../../releases) 下载最新版本，**开箱即用，无需安装任何依赖**：

| 平台 | 文件 | 说明 |
|------|------|------|
| macOS (Apple Silicon M1-M4) | `Temu.Assistant-*-arm64.dmg` | 推荐 |
| macOS (Intel) | `Temu.Assistant-*-x64.dmg` | Intel Mac |
| Windows 10/11 | `Temu.Assistant.Setup-*.exe` | x64 |

> ✅ **内置 Python 3.12 + openpyxl，无需安装 Python 或 Node.js**  
> 唯一前提：安装 [Google Chrome](https://www.google.com/chrome/)

### 本地开发运行

**前提条件**

- macOS 12+ 或 Windows 10+
- Google Chrome（已登录 Temu 账号）
- Python 3.10+（macOS 推荐 `/opt/homebrew/bin/python3`）
- Node.js 18+

**安装依赖**

```bash
pip3 install openpyxl requests websocket-client
```

**启动应用**

```bash
git clone https://github.com/howtimeschange/temu-assistant.git
cd temu-assistant/electron-app
npm install
npm start
```

---

## 📖 使用说明

### 1. 启动 Chrome

点击左上角「启动 Chrome」按钮，或确保 Chrome 已以 `--remote-debugging-port=9222` 参数启动。

### 2. 登录 Temu

在 Chrome 中登录 Temu 账号：
- 运营后台：`https://agentseller.temu.com`
- 店铺页面：`https://www.temu.com/mall.html?mall_id=你的mall_id`

### 3. 选择模块并运行

每个模块支持两种页面模式：
- **当前页面**：脚本在已打开的 tab 上操作
- **全新页面**：找不到对应 tab 时自动新开标签页

**商品数据时间筛选**

| 选项 | 说明 |
|------|------|
| 昨日 | 昨天一天的数据 |
| 近7日 | 最近7天 |
| 近30日 | 最近30天 |
| 自定义 | 手动填写开始/结束日期（最长31天） |

### 4. 查看输出

任务完成后，Excel 文件自动保存到桌面，点击「📂 输出文件」面板可快速定位。

---

## 🏗️ 技术架构

```
temu-assistant/
├── electron-app/          # Electron 前端
│   ├── src/
│   │   ├── main.js        # 主进程（IPC + Chrome 管理）
│   │   ├── preload.js     # 预加载脚本
│   │   └── renderer/      # 渲染进程（index.html + app.js）
│   └── assets/            # 图标资源
├── src/
│   ├── temu_utils.py      # CDP WebSocket 工具函数
│   └── temu_excel.py      # Excel 输出工具
├── temu_goods_data.py     # 商品数据抓取
├── temu_aftersales.py     # 售后数据抓取
├── temu_reviews.py        # 店铺评价抓取
└── temu_store_items.py    # 店铺商品抓取
```

### CDP 直连架构

所有抓取模块通过 CDP WebSocket 直连 Chrome（端口 9222），使用 Node.js `ws` 模块执行 JavaScript，无需 Playwright 或 Selenium。

```
Electron IPC → Python 子进程 → CDP WebSocket → Chrome Tab
```

### Beast 组件库适配

Temu 运营后台使用自研 Beast 组件库（非 antd），关键选择器：
- 表格行：`tbody tr.TB_tr_5-120-1`
- 分页：`li.PGT_next_5-120-1`
- 日期范围选择器：`PP_outerWrapper` 内含 `RPR_outerPickerWrapper` 的 portal 弹窗

---

## 📋 更新日志

### v1.0.4（2026-03-23）

**修复**
- 商品数据时间筛选失效：选项文字与页面实际文字不匹配（近7天→近7日，近30天→近30日），现已修正并加入向后兼容别名
- 最后一页出现重复数据行：翻页检测从「行数变化」改为「内容签名对比」，同时增加 `SPU|SKC` 去重，双重保障
- `_find_ws_module` 在开发模式下找不到 `ws` 模块导致所有 CDP 调用返回 `None`

**新增**
- 商品数据支持**自定义日期范围**：通过点击 Beast RPR 日历格子选择起止日期
  - 左右月面板完全独立控制（各有独立的 `<` `>` 箭头）
  - 支持跨月选择，前端+后端双重限制最长31天
- 时间筛选新增「昨日」选项

---

## 🛠️ 开发

```bash
# 安装依赖
cd electron-app && npm install

# 开发模式
npm start

# 打包 macOS DMG
npm run build:mac

# 打包 Windows NSIS
npm run build:win
```

---

## ❓ 常见问题

**macOS 提示「已损坏，无法打开」**

这是 macOS Gatekeeper 对未签名 app 的拦截。在终端执行：

```bash
xattr -cr "/Applications/Temu Assistant.app"
```

然后正常双击打开即可。

---

## 📄 许可证

MIT License

---

<p align="center">Made with ❤️ for Temu sellers</p>
