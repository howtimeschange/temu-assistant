"""
Temu 运营助手 — 店铺评价抓取
页面: https://www.temu.com/mall.html?mall_id=xxx
使用 CDP WebSocket 直连，点击「评价/Reviews」tab 后翻页抓取
"""
import sys
import os
import time
import re

sys.path.insert(0, os.path.dirname(__file__))
from src.temu_utils import (
    install_temu_adapters, desktop_path, timestamped_name,
    cdp_eval, cdp_navigate, get_tab_ws_url
)
from src.temu_excel import write_temu_excel

DOMAIN = "temu.com"


def click_reviews_tab(ws_url: str) -> bool:
    """点击「评价/Reviews」导航 tab"""
    js = """
    (function() {
      var navItems = document.querySelectorAll('h2._2kIA1PhC, h2[class*="_2kIA1PhC"]');
      for (var i = 0; i < navItems.length; i++) {
        var txt = navItems[i].innerText.trim();
        if (txt === '评价' || txt === 'Reviews' || txt.toLowerCase().startsWith('review')) {
          navItems[i].click();
          return 'clicked:' + txt;
        }
      }
      return 'not-found';
    })()
    """
    r = cdp_eval(ws_url, js)
    return str(r).startswith('clicked:')


def get_review_total(ws_url: str) -> int:
    """获取评价总数"""
    js = """
    (function() {
      // 找「132 评价」这样的文字
      var allEls = document.querySelectorAll('*');
      for (var i = 0; i < allEls.length; i++) {
        var txt = allEls[i].children.length === 0 && allEls[i].innerText ? allEls[i].innerText.trim() : '';
        var m = txt.match(/^(\\d[\\d,]+)\\s*(评价|Reviews?|review)/i);
        if (m) return parseInt(m[1].replace(',', ''));
      }
      return 0;
    })()
    """
    r = cdp_eval(ws_url, js)
    return int(r) if isinstance(r, (int, float)) else 0


def scrape_reviews_page(ws_url: str) -> list:
    """抓取当前页所有评价条目"""
    js = """
    (function() {
      var results = [];
      // 评价容器：div._3t3Ev35j
      var items = document.querySelectorAll('div._3t3Ev35j');
      for (var i = 0; i < items.length; i++) {
        var item = items[i];
        var r = {};

        // 用户名：div.XTEkYdlM
        var nameEl = item.querySelector('.XTEkYdlM');
        r.username = nameEl ? nameEl.innerText.trim() : '';

        // 购买日期 + 国家：div._1tSRIohB
        var dateEl = item.querySelector('._1tSRIohB');
        r.dateInfo = dateEl ? dateEl.innerText.trim().replace(/\\s+/g, ' ') : '';

        // 购买规格（颜色/尺码）
        var specEl = item.querySelector('[class*="_2Gy"], [class*="spec"], [class*="sku"]');
        r.spec = specEl ? specEl.innerText.trim() : '';

        // 评价文字（主体内容）
        // 找最长的文字节点
        var allText = Array.from(item.querySelectorAll('*'))
          .filter(function(el) { return el.children.length === 0 && el.innerText && el.innerText.trim().length > 20; })
          .map(function(el) { return el.innerText.trim(); });
        // 排除用户名和日期，取最长的
        r.reviewText = allText.filter(function(t) {
          return t !== r.username && !t.includes('购买于') && !t.includes('purchased') && t.length > 20;
        }).sort(function(a,b) { return b.length - a.length; })[0] || '';

        // 星级：找 aria-label 或 title 含星级的元素
        var starEl = item.querySelector('[aria-label*="star"], [title*="star"], [class*="star"], [class*="Star"]');
        r.stars = starEl ? (starEl.getAttribute('aria-label') || starEl.getAttribute('title') || '').replace(/[^0-9.]/g, '') : '';

        // 图片 URL
        var imgs = item.querySelectorAll('img');
        var imgUrls = [];
        for (var j = 0; j < imgs.length; j++) {
          var src = imgs[j].src || imgs[j].getAttribute('data-src') || '';
          if (src && !src.includes('avatar') && !src.includes('flag')) imgUrls.push(src);
        }
        r.images = imgUrls.join('|');

        if (r.username || r.reviewText) results.push(r);
      }
      return results;
    })()
    """
    result = cdp_eval(ws_url, js)
    if isinstance(result, list):
        return result
    return []


def has_next_page(ws_url: str) -> bool:
    """检查是否有下一页"""
    js = """
    (function() {
      var next = document.querySelector('li.temu-pagination-next');
      if (!next) return false;
      return next.getAttribute('aria-disabled') !== 'true' && !next.classList.contains('temu-pagination-disabled');
    })()
    """
    return bool(cdp_eval(ws_url, js))


def click_next_page(ws_url: str) -> bool:
    """点击下一页"""
    js = """
    (function() {
      var next = document.querySelector('li.temu-pagination-next');
      if (next && next.getAttribute('aria-disabled') !== 'true') {
        next.click(); return true;
      }
      return false;
    })()
    """
    return bool(cdp_eval(ws_url, js))


def wait_reviews_load(ws_url: str, old_count: int, timeout: int = 8) -> bool:
    """等待评价列表刷新"""
    start = time.time()
    while time.time() - start < timeout:
        time.sleep(0.5)
        count = cdp_eval(ws_url, "document.querySelectorAll('div._3t3Ev35j').length")
        if isinstance(count, int) and count != old_count:
            time.sleep(0.3)
            return True
    return False


def run(mall_url: str = "", output_path: str = None, print_fn=print):
    install_temu_adapters()

    if output_path is None:
        output_path = desktop_path(timestamped_name("temu_reviews"))

    ws_url = get_tab_ws_url(DOMAIN)
    if not ws_url:
        print_fn("❌ 未找到 temu.com 的 tab，请先在 Chrome 中打开店铺页面")
        return None

    # 如果提供了 URL，先导航
    if mall_url:
        print_fn(f"🔍 导航到店铺页面...")
        cdp_navigate(ws_url, mall_url)
        time.sleep(3)

    # 点击「评价」tab
    print_fn("📋 点击「评价」tab...")
    ok = click_reviews_tab(ws_url)
    if not ok:
        print_fn("⚠️ 未找到评价 tab，尝试继续...")
    time.sleep(1.5)

    total = get_review_total(ws_url)
    print_fn(f"  共 {total} 条评价")

    # 抓取所有页
    headers = ["用户名", "购买日期/国家", "购买规格", "评价内容", "星级", "图片链接"]
    all_rows = []
    page = 1

    while True:
        print_fn(f"  正在抓取第 {page} 页...")
        old_count = cdp_eval(ws_url, "document.querySelectorAll('div._3t3Ev35j').length")
        reviews = scrape_reviews_page(ws_url)
        print_fn(f"  ✓ 第 {page} 页获取 {len(reviews)} 条")

        for rv in reviews:
            all_rows.append([
                rv.get('username', ''),
                rv.get('dateInfo', ''),
                rv.get('spec', ''),
                rv.get('reviewText', ''),
                rv.get('stars', ''),
                rv.get('images', ''),
            ])

        if not has_next_page(ws_url):
            print_fn("  ↳ 已是最后一页")
            break

        click_next_page(ws_url)
        wait_reviews_load(ws_url, old_count if isinstance(old_count, int) else 0)
        page += 1
        time.sleep(0.5)

    if not all_rows:
        print_fn("⚠️ 未抓取到评价数据")
        return None

    write_temu_excel(output_path, [{"title": "店铺评价", "headers": headers, "rows": all_rows}])
    print_fn(f"\n✅ 完成！共 {len(all_rows)} 条，已保存到:\n   {output_path}")
    return output_path


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Temu 店铺评价抓取")
    parser.add_argument("--url", default="", help="店铺 URL（mall.html?mall_id=xxx）")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    run(mall_url=args.url, output_path=args.output)
