"""
Temu 运营助手 — 站点商品数据抓取（Items tab）
忽略 Explore Temu's picks 栏目，支持 See More 自动点击 + 翻页
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

DOMAIN = "www.temu.com"
LOGIN_WAIT = 40


def click_items_tab(tab: str) -> bool:
    """点击 Items tab"""
    js = """
    (function() {
      const tabs = Array.from(document.querySelectorAll('[role="tab"], [class*="tab"], button, a, li'));
      const itemTab = tabs.find(el => /^items?$/i.test(el.innerText.trim()) && el.offsetParent !== null);
      if (itemTab) {
        itemTab.click();
        return true;
      }
      return false;
    })()
    """
    r = bb(["eval", js, "--tab", tab], timeout=10)
    return r.stdout.strip().lower() == 'true'


def click_see_more(tab: str) -> bool:
    """点击 See More 按钮"""
    js = """
    (function() {
      const btns = Array.from(document.querySelectorAll('button, [role="button"], a, span'))
        .filter(el => /see more/i.test(el.innerText) && el.offsetParent !== null);
      if (btns.length > 0) {
        btns[0].click();
        return true;
      }
      return false;
    })()
    """
    r = bb(["eval", js, "--tab", tab], timeout=10)
    return r.stdout.strip().lower() == 'true'


def scrape_all_pages(tab: str, print_fn=print) -> list:
    """循环抓取所有商品分页"""
    all_items = []
    page = 1

    while True:
        print_fn(f"  第 {page} 页...")

        # 先尝试点 See More
        if click_see_more(tab):
            print_fn("  ↳ 点击 See More 加载更多...")
            time.sleep(2)

        data = bb_json(["site", "temu/store-items"])

        if "error" in data:
            print_fn(f"  ⚠️  抓取出错: {data['error']}")
            break

        items = data.get("items", [])
        all_items.extend(items)
        print_fn(f"  ✓ 获取 {len(items)} 件商品（累计 {len(all_items)}）")

        if not data.get("hasNextPage", False):
            break

        clicked = click_next_page(tab)
        if not clicked:
            # 尝试滚动到底部触发加载
            bb(["eval", "window.scrollTo(0, document.body.scrollHeight)", "--tab", tab])
            time.sleep(2.5)
            data2 = bb_json(["site", "temu/store-items"])
            new_items = data2.get("items", [])
            if len(new_items) <= len(items):
                print_fn("  ↳ 无更多商品，停止")
                break
            all_items.extend(new_items[len(items):])
        else:
            time.sleep(2.5)

        page += 1

    return all_items


def run(shop_url: str, output_path: str = None, login_wait: int = LOGIN_WAIT, print_fn=print):
    install_temu_adapters()

    if output_path is None:
        output_path = desktop_path(timestamped_name("temu_store_items"))

    print_fn(f"🔗 打开店铺链接: {shop_url}")
    tab = get_tab_by_domain(DOMAIN)

    if tab:
        navigate_tab(tab, shop_url)
    else:
        tab = open_new_tab(shop_url)

    time.sleep(3)

    # 检查登录验证
    js_check = """document.querySelector('[class*="login"], [class*="verify"]') ? 'need-login' : 'ok'"""
    r = bb(["eval", js_check, "--tab", tab], timeout=8)
    if "need-login" in (r.stdout or ""):
        print_fn(f"⏳ 检测到登录验证，请在 {login_wait}s 内完成操作...")
        time.sleep(login_wait)

    print_fn("🔍 等待页面加载...")
    time.sleep(2)

    # 点击 Items tab
    print_fn("📦 点击 Items tab...")
    for _ in range(3):
        if click_items_tab(tab):
            print_fn("  ✓ 已点击 Items tab")
            break
        time.sleep(1)
    else:
        print_fn("  ⚠️  未找到 Items tab，继续尝试抓取当前页...")

    time.sleep(2.5)
    wait_for_selector(tab, '[class*="goods"], [class*="product"], [class*="item"]', max_wait=15)

    print_fn("🚀 开始抓取商品数据...")
    items = scrape_all_pages(tab, print_fn)

    if not items:
        print_fn("⚠️  未抓取到商品数据")
        return None

    headers = ["商品名", "价格", "原价", "评分", "评价数", "商品链接", "图片URL"]
    rows = [
        [i.get("name",""), i.get("price",""), i.get("originalPrice",""),
         i.get("rating",""), i.get("reviewCount",""), i.get("href",""), i.get("imgSrc","")]
        for i in items
    ]

    write_temu_excel(output_path, [{"title": "店铺商品", "headers": headers, "rows": rows}])
    print_fn(f"\n✅ 完成！共 {len(rows)} 件商品（已排除 Explore Temu's picks），文件:\n   {output_path}")
    return output_path


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Temu 站点商品抓取")
    parser.add_argument("url", help="店铺链接")
    parser.add_argument("--output", default=None)
    parser.add_argument("--wait", type=int, default=40)
    args = parser.parse_args()
    run(shop_url=args.url, output_path=args.output, login_wait=args.wait)
