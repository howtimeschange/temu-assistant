"""
Temu 运营助手 — 商品数据抓取
页面: https://agentseller.temu.com/newon/goods-data
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(__file__))
from src.temu_utils import (
    bb, bb_json, get_tab_by_domain, open_new_tab, navigate_tab,
    wait_for_selector, click_next_page, install_temu_adapters,
    desktop_path, timestamped_name
)
from src.temu_excel import write_temu_excel

GOODS_URL = "https://agentseller.temu.com/newon/goods-data"
LOGIN_URL  = "https://agentseller.temu.com/"
DOMAIN     = "agentseller.temu.com"

def set_date_filter(tab: str, start_date: str, end_date: str):
    """通过 eval 注入 JS 设置日期筛选"""
    # Temu 后台通常是 ant-design DatePicker，尝试通过 React fiber 设置值
    js = f"""
    (async function() {{
      // 找 datepicker 输入框并设置
      const inputs = document.querySelectorAll('.ant-picker-input input, [class*="date-picker"] input, [class*="datepicker"] input');
      if (inputs.length >= 2) {{
        const startInput = inputs[0];
        const endInput = inputs[1];
        // 模拟用户输入
        function setVal(el, val) {{
          el.focus();
          el.value = val;
          el.dispatchEvent(new Event('input', {{bubbles: true}}));
          el.dispatchEvent(new Event('change', {{bubbles: true}}));
        }}
        setVal(startInput, '{start_date}');
        await new Promise(r => setTimeout(r, 300));
        setVal(endInput, '{end_date}');
        await new Promise(r => setTimeout(r, 300));
        // 按 Enter 确认
        endInput.dispatchEvent(new KeyboardEvent('keydown', {{key: 'Enter', bubbles: true}}));
        return 'ok';
      }}
      // 找日期范围按钮
      const rangeBtn = document.querySelector('[class*="date-range"], [class*="dateRange"]');
      if (rangeBtn) {{
        rangeBtn.click();
        await new Promise(r => setTimeout(r, 500));
      }}
      return 'no-input-found';
    }})()
    """
    r = bb(["eval", js, "--tab", tab], timeout=10)
    return r.stdout.strip()


def scrape_all_pages(tab: str, console_print=print) -> tuple[list, list]:
    """循环抓取所有分页，返回 (headers, all_rows)"""
    all_rows = []
    headers  = []
    page = 1

    while True:
        console_print(f"  正在抓取第 {page} 页...")
        data = bb_json(["site", "temu/goods-data"])

        if "error" in data:
            console_print(f"  ⚠️  第 {page} 页抓取出错: {data['error']}")
            break

        if not headers and data.get("headers"):
            headers = data["headers"]

        rows = data.get("items", [])
        all_rows.extend(rows)
        console_print(f"  ✓ 第 {page} 页获取 {len(rows)} 条")

        if not data.get("hasNextPage", False):
            break

        # 翻页
        clicked = click_next_page(tab)
        if not clicked:
            console_print("  ↳ 未找到下一页按钮，停止")
            break

        time.sleep(2.5)  # 等待数据加载
        page += 1

    return headers, all_rows


def run(mode: str = "current", start_date: str = "", end_date: str = "",
        output_path: str = None, login_wait: int = 40, print_fn=print):
    """
    mode: 'current'（在当前页面）或 'new'（全新页面）
    start_date/end_date: 'YYYY-MM-DD'
    output_path: 输出文件路径（默认桌面）
    """
    install_temu_adapters()

    if output_path is None:
        output_path = desktop_path(timestamped_name("temu_goods_data"))

    tab = None

    if mode == "new":
        print_fn(f"📂 新开页面，导航到 {LOGIN_URL}")
        tab = open_new_tab(LOGIN_URL)
        print_fn(f"⏳ 请在 {login_wait}s 内完成登录并切换到目标站点/店铺...")
        time.sleep(login_wait)
        # 导航到商品数据页
        navigate_tab(tab, GOODS_URL)
        time.sleep(3)
    else:
        print_fn(f"🔍 在当前已登录页面操作...")
        tab = get_tab_by_domain(DOMAIN)
        if not tab:
            print_fn(f"⚠️  未找到 {DOMAIN} 的 tab，尝试新开页面...")
            tab = open_new_tab(GOODS_URL)
            time.sleep(5)
        else:
            navigate_tab(tab, GOODS_URL)
            time.sleep(3)

    if tab is None:
        print_fn("❌ 无法找到或打开 tab，退出")
        return None

    # 等待页面加载
    print_fn("⏳ 等待页面加载...")
    wait_for_selector(tab, 'table, [class*="table"]', max_wait=20)
    time.sleep(2)

    # 设置日期筛选
    if start_date and end_date:
        print_fn(f"📅 设置时间筛选: {start_date} ~ {end_date}")
        result = set_date_filter(tab, start_date, end_date)
        print_fn(f"  筛选状态: {result}")
        time.sleep(2.5)

    # 开始抓取
    print_fn("🚀 开始抓取商品数据...")
    headers, rows = scrape_all_pages(tab, print_fn)

    if not rows:
        print_fn("⚠️  未抓取到任何数据，请检查页面状态")
        return None

    # 如果表头为空，用列序号
    if not headers:
        max_cols = max(len(r) for r in rows) if rows else 0
        headers = [f"列{i+1}" for i in range(max_cols)]

    # 写 Excel
    write_temu_excel(output_path, [{"title": "商品数据", "headers": headers, "rows": rows}])
    print_fn(f"\n✅ 完成！共 {len(rows)} 条，文件已保存到:\n   {output_path}")
    return output_path


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Temu 商品数据抓取")
    parser.add_argument("--mode", choices=["current", "new"], default="current")
    parser.add_argument("--start", default="", help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end",   default="", help="结束日期 YYYY-MM-DD")
    parser.add_argument("--output", default=None)
    parser.add_argument("--wait",  type=int, default=40)
    args = parser.parse_args()
    run(mode=args.mode, start_date=args.start, end_date=args.end,
        output_path=args.output, login_wait=args.wait)
