"""
Temu 运营助手 — 售后数据抓取
页面: https://agentseller.temu.com/main/aftersales/information
支持全球 / 美国 / 欧区切换
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(__file__))
from src.temu_utils import (
    bb, bb_json, get_tab_by_domain, open_new_tab, navigate_tab,
    wait_for_selector, click_next_page, close_popup, install_temu_adapters,
    desktop_path, timestamped_name
)
from src.temu_excel import write_temu_excel

AFTERSALES_URL = "https://agentseller.temu.com/main/aftersales/information"
LOGIN_URL      = "https://agentseller.temu.com/"
DOMAIN         = "agentseller.temu.com"

# 地区配置：显示名 → 点击目标文本（根据实际页面可能需要调整）
REGIONS = {
    "全球": "All",
    "美国": "United States",
    "欧区": "Europe",
}


def switch_region(tab: str, region_text: str) -> bool:
    """切换地区（点击对应的地区 tab/选项）"""
    js = f"""
    (function() {{
      const allEls = Array.from(document.querySelectorAll('button, [role="tab"], li, a, span'));
      const target = allEls.find(el => {{
        const t = el.innerText.trim();
        return t === '{region_text}' || t.includes('{region_text}');
      }});
      if (target && target.offsetParent !== null) {{
        target.click();
        return true;
      }}
      return false;
    }})()
    """
    r = bb(["eval", js, "--tab", tab], timeout=10)
    return r.stdout.strip().lower() == 'true'


def scrape_all_pages(tab: str, region: str, print_fn=print) -> tuple[list, list]:
    """循环抓取所有分页"""
    all_rows = []
    headers  = []
    page = 1

    while True:
        print_fn(f"  [{region}] 第 {page} 页...")

        # 先处理弹窗
        popup = close_popup(tab)
        if popup["closed"]:
            print_fn(f"  ↳ 自动关闭了弹窗")
            time.sleep(1)
        elif popup["still_visible"]:
            print_fn(f"  ⚠️  检测到弹窗无法自动关闭，请手动处理后按 Enter 继续...")
            input()

        data = bb_json(["site", "temu/aftersales"])

        if "error" in data:
            print_fn(f"  ⚠️  抓取出错: {data['error']}")
            break

        if not headers and data.get("headers"):
            headers = data["headers"]

        rows = data.get("items", [])
        all_rows.extend(rows)
        print_fn(f"  ✓ 获取 {len(rows)} 条（累计 {len(all_rows)}）")

        if not data.get("hasNextPage", False):
            break

        clicked = click_next_page(tab)
        if not clicked:
            print_fn("  ↳ 未找到下一页，停止")
            break

        time.sleep(2.5)
        page += 1

    return headers, all_rows


def run(mode: str = "current", regions: list = None, output_path: str = None,
        login_wait: int = 40, print_fn=print):
    """
    mode: 'current' 或 'new'
    regions: 要抓取的地区列表，如 ['全球', '美国', '欧区']，默认全抓
    """
    install_temu_adapters()

    if regions is None:
        regions = list(REGIONS.keys())

    if output_path is None:
        output_path = desktop_path(timestamped_name("temu_aftersales"))

    tab = None

    if mode == "new":
        print_fn(f"📂 新开页面，导航到 {LOGIN_URL}")
        tab = open_new_tab(LOGIN_URL)
        print_fn(f"⏳ 请在 {login_wait}s 内完成登录并切换到目标站点/店铺...")
        time.sleep(login_wait)
        navigate_tab(tab, AFTERSALES_URL)
        time.sleep(3)
    else:
        print_fn(f"🔍 使用当前已登录页面...")
        tab = get_tab_by_domain(DOMAIN)
        if not tab:
            print_fn("⚠️  未找到 agentseller.temu.com tab，尝试新开...")
            tab = open_new_tab(AFTERSALES_URL)
            time.sleep(5)
        else:
            navigate_tab(tab, AFTERSALES_URL)
            time.sleep(3)

    if tab is None:
        print_fn("❌ 无法获取 tab，退出")
        return None

    print_fn("⏳ 等待售后页面加载...")
    wait_for_selector(tab, 'table, [class*="table"]', max_wait=20)
    time.sleep(2)

    all_sheets = []

    for region in regions:
        region_text = REGIONS.get(region, region)
        print_fn(f"\n🌍 切换到地区: {region} ({region_text})")

        success = switch_region(tab, region_text)
        if not success:
            print_fn(f"  ⚠️  未找到 {region} 地区按钮，跳过")
            continue

        time.sleep(2.5)
        headers, rows = scrape_all_pages(tab, region, print_fn)

        if not headers:
            max_cols = max(len(r) for r in rows) if rows else 0
            headers = [f"列{i+1}" for i in range(max_cols)]

        all_sheets.append({"title": region, "headers": headers, "rows": rows})
        print_fn(f"  ✅ {region} 共 {len(rows)} 条")

    if not all_sheets:
        print_fn("⚠️  未抓取到任何数据")
        return None

    write_temu_excel(output_path, all_sheets)
    total = sum(len(s["rows"]) for s in all_sheets)
    print_fn(f"\n✅ 完成！{len(all_sheets)} 个地区，共 {total} 条，文件:\n   {output_path}")
    return output_path


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Temu 售后数据抓取")
    parser.add_argument("--mode", choices=["current", "new"], default="current")
    parser.add_argument("--regions", nargs="+", choices=list(REGIONS.keys()), default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--wait",  type=int, default=40)
    args = parser.parse_args()
    run(mode=args.mode, regions=args.regions, output_path=args.output, login_wait=args.wait)
