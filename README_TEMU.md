# Temu 运营助手

基于 [jd-price-monitor](https://github.com/howtimeschange/jd-price-monitor) 架构改造，使用 **bb-browser + CDP** 方案抓取 Temu 商家后台与店铺前台数据。

---

## 前置条件

与 jd-price-monitor 相同：

1. Chrome 以 Remote Debugging 模式运行：
   ```bash
   # macOS
   open -a "Google Chrome" --args --remote-debugging-port=9222
   ```

2. bb-browser daemon 保持运行：
   ```bash
   node $(npm root -g)/bb-browser/dist/daemon.js
   ```

3. Python 依赖（首次运行自动安装）：
   ```bash
   pip install rich questionary openpyxl pyyaml
   ```

---

## 启动

```bash
python temu_cli.py
```

交互式菜单：

```
🛍️  Temu 运营助手   Powered by bb-browser + CDP

CDP 端口 9222   bb-browser + Chrome Remote Debugging

请选择功能：
  📦  后台-商品数据抓取
  🔄  后台-售后数据抓取
  ⭐  店铺评价抓取
  🏪  站点商品数据抓取
  ⚙️   设置
  ❌  退出
```

---

## 功能说明

### 📦 后台-商品数据抓取

- **页面**：`https://agentseller.temu.com/newon/goods-data`
- **登录模式**：
  - **在当前页面**：使用已打开的登录态 tab 直接操作
  - **全新页面**：新开 tab 打开 Temu 后台，等待用户登录并切换站点/店铺（30-50s）
- **时间筛选**：可选，输入 `YYYY-MM-DD` 自动在页面设置
- **输出**：`temu_goods_data_YYYYMMDD_HHMMSS.xlsx`（默认桌面）

直接运行：
```bash
python temu_goods_data.py --mode current --start 2025-01-01 --end 2025-01-31
python temu_goods_data.py --mode new --wait 45
```

---

### 🔄 后台-售后数据抓取

- **页面**：`https://agentseller.temu.com/main/aftersales/information`
- **地区**：全球 / 美国 / 欧区（每个地区一个 Sheet）
- **弹窗处理**：自动尝试关闭，无法关闭则暂停等人介入
- **输出**：`temu_aftersales_YYYYMMDD_HHMMSS.xlsx`（每个地区一个 sheet）

直接运行：
```bash
python temu_aftersales.py --mode current --regions 全球 美国
python temu_aftersales.py --mode new --wait 45
```

---

### ⭐ 店铺评价抓取

- 输入店铺链接，自动点击 **Reviews** tab
- 抓取：评分、评价文字、时间、用户、商品名、图片 URL
- 自动翻页
- **输出**：`temu_reviews_YYYYMMDD_HHMMSS.xlsx`

直接运行：
```bash
python temu_reviews.py "https://www.temu.com/mall.html?mall_id=634418216574527&..."
```

---

### 🏪 站点商品数据抓取

- 输入店铺链接，自动点击 **Items** tab
- 忽略 **Explore Temu's picks** 栏目（其他店铺商品）
- 自动点击 **See More** 按钮，自动翻页
- 抓取：商品名、价格、原价、评分、评价数、链接、图片
- **输出**：`temu_store_items_YYYYMMDD_HHMMSS.xlsx`

直接运行：
```bash
python temu_store_items.py "https://www.temu.com/mall.html?mall_id=634418216574527&..."
```

---

## 项目结构

```
temu-assistant/
├── temu_cli.py              # 🎯 主入口（交互式菜单）
├── temu_goods_data.py       # 商品数据抓取
├── temu_aftersales.py       # 售后数据抓取
├── temu_reviews.py          # 店铺评价抓取
├── temu_store_items.py      # 站点商品数据抓取
├── config.yaml              # 配置文件
├── adapters/
│   ├── jd/                  # 原 JD adapter（保留）
│   └── temu/
│       ├── goods-data.js    # 商品数据页 adapter
│       ├── aftersales.js    # 售后数据 adapter
│       ├── reviews.js       # 评价列表 adapter
│       └── store-items.js   # 店铺商品 adapter
└── src/
    ├── temu_utils.py        # 公共工具（bb-browser 封装）
    └── temu_excel.py        # Excel 导出工具
```

---

## 注意事项

- bb-browser daemon 和 Chrome 必须保持运行
- Temu 页面为 React SPA，适配器使用动态等待而非固定延迟
- 若页面结构更新导致抓取失败，需更新 `adapters/temu/*.js` 中的 CSS 选择器
- 首次运行时程序会自动将 temu adapters 安装到 `~/.bb-browser/sites/temu/`
