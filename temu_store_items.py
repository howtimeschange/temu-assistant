"""
Temu 运营助手 — 店铺商品抓取
页面: https://www.temu.com/mall.html?mall_id=xxx
使用 CDP WebSocket 直连，点击「商品/Items」tab 后翻页抓取
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


def click_items_tab(ws_url: str) -> bool:
    """点击「商品/Items」导航 tab"""
    js = """
    (function() {
      var navItems = document.querySelectorAll('h2._2kIA1PhC, h2[class*="_2kIA1PhC"]');
      for (var i = 0; i < navItems.length; i++) {
        var txt = navItems[i].innerText.trim();
        if (txt === '商品' || txt === 'Items' || txt.toLowerCase() === 'items') {
          navItems[i].click();
          return 'clicked:' + txt;
        }
      }
      return 'not-found';
    })()
    """
    r = cdp_eval(ws_url, js)
    return str(r).startswith('clicked:')


def scrape_items_page(ws_url: str) -> list:
    """抓取当前页所有商品"""
    js = """
    (function() {
      var results = [];
      // 商品卡片容器：div._6q6qVUF5._1UrrHYym（包含图片+名称+价格+销量）
      var cards = document.querySelectorAll('div._6q6qVUF5._1UrrHYym');
      if (cards.length === 0) {
        // 降级：找包含「已售」和商品链接的容器
        var allDivs = document.querySelectorAll('div[data-tooltip*="goodContainer"]');
        if (allDivs.length > 0) cards = allDivs;
      }

      for (var i = 0; i < cards.length; i++) {
        var card = cards[i];
        var r = {};

        // 商品链接（href 含 -g-）
        var linkEl = card.querySelector('a[href*="-g-"]');
        r.url = linkEl ? linkEl.href : '';

        // 商品名（data-tooltip-title 最可靠）
        r.name = card.getAttribute('data-tooltip-title') || '';
        if (!r.name && linkEl) {
          r.name = linkEl.innerText.trim().replace(/在新标签页中打开。/g, '').trim().split('\\n')[0];
        }

        // 图片（找主图，data-js-main-img=true 或最大尺寸的）
        var mainImg = card.querySelector('img[data-js-main-img="true"]') || card.querySelector('img[src*="kwcdn"]');
        r.image = mainImg ? mainImg.src : '';

        // 价格（找所有文字节点，匹配货币格式）
        var allEls = card.querySelectorAll('*');
        var prices = [];
        for (var j = 0; j < allEls.length; j++) {
          var el = allEls[j];
          var txt = el.children.length === 0 && el.innerText ? el.innerText.trim() : '';
          if (txt.match(/^[A-Z]{0,3}\\$[\\d\\.]+$/) || txt.match(/^[¥€£][\\d,\\.]+$/)) {
            prices.push(txt);
          }
        }
        // 去重，第一个是现价，第二个（如果有）是原价
        var unique = prices.filter(function(v, i, a) { return a.indexOf(v) === i; });
        r.price = unique[0] || '';
        r.originalPrice = unique[1] || '';

        // 销量
        var soldEl = card.querySelector('._2XgTiMJi, [class*="soldCount"], [class*="sold_count"]');
        if (!soldEl) {
          // 降级：找含「已售」的叶子节点
          for (var j = 0; j < allEls.length; j++) {
            var t = allEls[j].children.length === 0 && allEls[j].innerText ? allEls[j].innerText.trim() : '';
            if (t.match(/^已售\\d/) || t.toLowerCase().match(/^\\d.*sold/)) {
              r.sold = t; break;
            }
          }
        } else {
          r.sold = soldEl.innerText.trim();
        }

        // goods_id from URL or data-tooltip
        var tooltip = card.getAttribute('data-tooltip') || '';
        var m1 = tooltip.match(/goodContainer-(\\d+)/);
        r.goodsId = m1 ? m1[1] : (r.url.match(/g-(\\d+)\\.html/) || ['', ''])[1];

        if (r.name || r.url) results.push(r);
      }
      return results;
    })()
    """
    result = cdp_eval(ws_url, js)
    if isinstance(result, list):
        return result
    return []


def has_next_page(ws_url: str) -> bool:
    js = """
    (function() {
      var next = document.querySelector('li.temu-pagination-next');
      if (!next) return false;
      return next.getAttribute('aria-disabled') !== 'true' && !next.classList.contains('temu-pagination-disabled');
    })()
    """
    return bool(cdp_eval(ws_url, js))


def click_next_page(ws_url: str) -> bool:
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


def wait_items_load(ws_url: str, old_count: int, timeout: int = 8) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        time.sleep(0.5)
        count = cdp_eval(ws_url, "document.querySelectorAll('div._6q6qVUF5._1UrrHYym').length")
        if isinstance(count, int) and count != old_count:
            time.sleep(0.3)
            return True
    return False


def run(mall_url: str = "", output_path: str = None, print_fn=print):
    install_temu_adapters()

    if output_path is None:
        output_path = desktop_path(timestamped_name("temu_store_items"))

    ws_url = get_tab_ws_url(DOMAIN)
    if not ws_url:
        print_fn("❌ 未找到 temu.com 的 tab，请先在 Chrome 中打开店铺页面")
        return None

    if mall_url:
        print_fn(f"🔍 导航到店铺页面...")
        cdp_navigate(ws_url, mall_url)
        time.sleep(3)

    # 点击「商品」tab
    print_fn("📦 点击「商品」tab...")
    ok = click_items_tab(ws_url)
    if not ok:
        print_fn("⚠️ 未找到商品 tab，尝试继续抓取当前内容...")
    time.sleep(2)

    # 抓取所有页
    headers = ["商品名称", "商品链接", "价格", "原价", "商品图片", "销量", "goods_id"]
    all_rows = []
    page = 1

    while True:
        print_fn(f"  正在抓取第 {page} 页...")
        old_count = cdp_eval(ws_url, "document.querySelectorAll('div._6q6qVUF5._1UrrHYym').length")
        items = scrape_items_page(ws_url)
        print_fn(f"  ✓ 第 {page} 页获取 {len(items)} 条")

        for item in items:
            all_rows.append([
                item.get('name', ''),
                item.get('url', ''),
                item.get('price', ''),
                item.get('originalPrice', ''),
                item.get('image', ''),
                item.get('sold', ''),
                item.get('goodsId', ''),
            ])

        if not has_next_page(ws_url):
            print_fn("  ↳ 已是最后一页")
            break

        cur_count = cdp_eval(ws_url, "document.querySelectorAll('div._6q6qVUF5._1UrrHYym').length")
        click_next_page(ws_url)
        wait_items_load(ws_url, cur_count if isinstance(cur_count, int) else 0)
        page += 1
        time.sleep(0.5)

    if not all_rows:
        print_fn("⚠️ 未抓取到商品数据")
        return None

    write_temu_excel(output_path, [{"title": "店铺商品", "headers": headers, "rows": all_rows}])
    print_fn(f"\n✅ 完成！共 {len(all_rows)} 条，已保存到:\n   {output_path}")
    return output_path


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Temu 店铺商品抓取")
    parser.add_argument("--url", default="", help="店铺 URL（mall.html?mall_id=xxx）")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    run(mall_url=args.url, output_path=args.output)
