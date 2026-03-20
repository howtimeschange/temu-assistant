"""
Temu 运营助手 — 店铺评价抓取
输入店铺链接，点击 Reviews tab，抓取全量评价
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


def click_reviews_tab(tab: str) -> bool:
    """点击 Reviews tab"""
    js = """
    (function() {
      const tabs = Array.from(document.querySelectorAll('[role="tab"], [class*="tab"], button, a, li'));
      const reviewTab = tabs.find(el => /reviews?/i.test(el.innerText.trim()) && el.offsetParent !== null);
      if (reviewTab) {
        reviewTab.click();
        return true;
      }
      return false;
    })()
    """
    r = bb(["eval", js, "--tab", tab], timeout=10)
    return r.stdout.strip().lower() == 'true'


def scrape_all_pages(tab: str, print_fn=print) -> list:
    """循环抓取所有评价分页"""
    all_reviews = []
    page = 1

    while True:
        print_fn(f"  第 {page} 页...")
        data = bb_json(["site", "temu/reviews"])

        if "error" in data:
            print_fn(f"  ⚠️  抓取出错: {data['error']}")
            break

        reviews = data.get("reviews", [])
        all_reviews.extend(reviews)
        print_fn(f"  ✓ 获取 {len(reviews)} 条评价（累计 {len(all_reviews)}）")

        if not data.get("hasNextPage", False):
            break

        clicked = click_next_page(tab)
        if not clicked:
            # 尝试滚动触发加载更多
            bb(["eval", "window.scrollTo(0, document.body.scrollHeight)", "--tab", tab])
            time.sleep(2)
            data2 = bb_json(["site", "temu/reviews"])
            new_reviews = data2.get("reviews", [])
            if len(new_reviews) <= len(reviews):
                print_fn("  ↳ 无更多内容，停止")
                break
        else:
            time.sleep(2.5)

        page += 1

    return all_reviews


def run(shop_url: str, output_path: str = None, login_wait: int = LOGIN_WAIT, print_fn=print):
    install_temu_adapters()

    if output_path is None:
        output_path = desktop_path(timestamped_name("temu_reviews"))

    print_fn(f"🔗 打开店铺链接: {shop_url}")
    tab = get_tab_by_domain(DOMAIN)

    if tab:
        navigate_tab(tab, shop_url)
    else:
        tab = open_new_tab(shop_url)

    time.sleep(3)

    # 检查是否有登录验证
    js_check = """document.querySelector('[class*="login"], [class*="verify"], #login-modal') ? 'need-login' : 'ok'"""
    r = bb(["eval", js_check, "--tab", tab], timeout=8)
    if "need-login" in (r.stdout or ""):
        print_fn(f"⏳ 检测到登录验证，请在 {login_wait}s 内完成操作...")
        time.sleep(login_wait)

    print_fn("🔍 等待页面加载完成...")
    time.sleep(2)

    # 点击 Reviews tab
    print_fn("📝 点击 Reviews tab...")
    for _ in range(3):
        if click_reviews_tab(tab):
            print_fn("  ✓ 已点击 Reviews tab")
            break
        time.sleep(1)
    else:
        print_fn("  ⚠️  未找到 Reviews tab，继续尝试抓取当前页...")

    time.sleep(2.5)
    wait_for_selector(tab, '[class*="review"], [class*="comment"]', max_wait=15)

    print_fn("🚀 开始抓取评价...")
    reviews = scrape_all_pages(tab, print_fn)

    if not reviews:
        print_fn("⚠️  未抓取到评价数据")
        return None

    headers = ["评分", "评价内容", "时间", "用户", "商品名", "图片URL"]
    rows = [
        [r.get("rating",""), r.get("text",""), r.get("time",""),
         r.get("username",""), r.get("goodsName",""), r.get("images","")]
        for r in reviews
    ]

    write_temu_excel(output_path, [{"title": "店铺评价", "headers": headers, "rows": rows}])
    print_fn(f"\n✅ 完成！共 {len(rows)} 条评价，文件:\n   {output_path}")
    return output_path


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Temu 店铺评价抓取")
    parser.add_argument("url", help="店铺链接")
    parser.add_argument("--output", default=None)
    parser.add_argument("--wait", type=int, default=40)
    args = parser.parse_args()
    run(shop_url=args.url, output_path=args.output, login_wait=args.wait)
