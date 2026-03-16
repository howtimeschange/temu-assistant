# JD Price Monitor（京东价格监控）

> 监控京东自营店铺所有 SKU 的前台价格，自动发现破价商品，通过钉钉推送告警。

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
    ⏰  创建系统定时任务（cron）
    ⚙️   设置  —  店铺 / 阈值 / Webhook
    ❌  退出
```

**设置菜单**支持：
- 粘贴任意京东店铺 URL，自动解析 shop_id
- 修改破价阈值（如输入 `50` 即 5折）
- 配置钉钉 Webhook，支持加签 + 一键测试发送
- 修改巡检间隔

**循环巡检**支持前台运行和后台进程两种模式。

**定时任务**支持自动写入 crontab（macOS/Linux）或复制到剪贴板（Windows）。

---

## 项目结构

```
jd-price-monitor/
├── setup.sh                  # 远程一键安装入口（macOS / Linux，curl | bash）
├── setup.ps1                 # 远程一键安装入口（Windows，irm | iex）
├── install.sh                # 本地安装脚本（macOS / Linux）
├── install.bat               # 本地安装脚本（Windows CMD）
├── install.ps1               # 本地安装脚本（Windows PowerShell）
├── cli.py                    # ✨ 交互式 CLI 入口
├── config.yaml               # 主配置文件
├── main.py                   # 巡检核心逻辑（可独立运行）
├── scrape_list.py            # 价格导出核心逻辑（可独立运行）
├── requirements.txt          # Python 依赖
├── crontab.example           # 定时任务示例
├── adapters/
│   └── jd/
│       └── shop-prices.js    # bb-browser 适配器
└── src/
    ├── config.py             # 配置加载 & 保存
    ├── checker.py            # 破价检测逻辑
    ├── dingtalk.py           # 钉钉告警
    └── storage.py            # 历史记录存储
```

## 命令行直接运行（无 CLI）

```bash
# 导出价格 Excel
venv/bin/python scrape_list.py        # macOS/Linux
venv\Scripts\python scrape_list.py   # Windows

# 单次巡检
venv/bin/python main.py

# 循环巡检
venv/bin/python main.py --loop
```

---

## 工作原理

```
cli.py / scrape_list.py
│
├── bb-browser tab list          # 找到 mall.jd.com tab
├── bb-browser eval navigate     # 切换到目标页，等待 25s
└── bb-browser site jd/shop-prices   # 在浏览器内执行 adapter
    │
    ├── 等待价格元素渲染（最多 5s）
    ├── 分段滚动（10 步）触发懒加载价格
    ├── 读取 DOM：SKU ID / 名称 / 价格 / 链接
    ├── XHR 补查 p.3.cn（针对仍为空的价格）
    └── 返回 JSON + nextUrl（下一页链接）
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
- 吊牌价来源于商品列表页的划线价；若京东未展示划线价，该 SKU 跳过检测
- 建议在 Mac 不休眠状态下运行，或部署到 Windows Server / Linux VPS（需要有图形界面支持 Chrome）
- `cookies.json` 已加入 `.gitignore`，不会被提交

## License

MIT
