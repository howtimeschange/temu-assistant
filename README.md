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
├── requirements.txt              # Python 依赖
├── crontab.example               # 定时任务示例
├── adapters/
│   └── jd/
│       ├── shop-prices.js        # bb-browser 列表页 adapter
│       └── item-price.js         # bb-browser 详情页 adapter（兜底）
└── src/
    ├── config.py                 # 配置加载 & 保存
    ├── checker.py                # 破价检测逻辑
    ├── dingtalk.py               # 钉钉告警
    ├── excel_writer.py           # Excel 导出（含兜底标记高亮）
    ├── sku_fetcher.py            # SKU + 价格抓取（含兜底补全）
    └── storage.py                # 历史记录存储
```

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
