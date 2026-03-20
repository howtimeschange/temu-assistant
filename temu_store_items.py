"""
Temu 运营助手 — 店铺商品抓取
页面: https://www.temu.com/mall.html?mall_id=xxx
使用 CDP WebSocket 直连，点击「商品/Items」tab，滚动加载全量商品
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(__file__))
from src.temu_utils import (
    install_temu_adapters, desktop_path, timestamped_name,
    cdp_eval, cdp_navigate, get_tab_ws_url
)
from src.temu_excel import write_temu_excel

DOMAIN = "temu.com/mall"  # 精确匹配 mall 页面，避免误选 bgn_verification tab


def click_items_tab(ws_url: str, wait_timeout: int = 10) -> bool:
    """等待 nav 渲染完成后点击「商品/Items」tab"""
    start = time.time()
    while time.time() - start < wait_timeout:
        count = cdp_eval(ws_url, "document.querySelectorAll('h2._2kIA1PhC').length")
        if isinstance(count, int) and count > 0:
            break
        time.sleep(0.5)

    js = """
    (function() {
      var navItems = document.querySelectorAll('h2._2kIA1PhC');
      for (var i = 0; i < navItems.length; i++) {
        var txt = navItems[i].innerText.trim();
        if (txt === '商品' || txt === 'Items') {
          navItems[i].click();
          return 'clicked:' + txt;
        }
      }
      return 'not-found:count=' + navItems.length;
    })()
    """
    r = cdp_eval(ws_url, js)
    return str(r).startswith('clicked:')


def get_goods_total(ws_url: str) -> int:
    """获取店铺商品总数（「175 商品」区域）"""
    js = """
    (function() {
      // 找「175 商品」：_17RAYb2C._2vH-84kZ 中包含文字「商品」标签的那个
      var containers = document.querySelectorAll('._17RAYb2C._2vH-84kZ');
      for (var i=0; i<containers.length; i++) {
        var text = containers[i].innerText.trim();
        if (text.includes('商品') || text.includes('Items')) {
          var numEl = containers[i].querySelector('._2VVwJmfY');
          if (numEl) return parseInt(numEl.innerText.trim().replace(/,/g, '')) || 0;
        }
      }
      // 降级：找「_25EQ1kor」中「175 商品」这样的文本
      var countEl = document.querySelector('._25EQ1kor');
      if (countEl) {
        var m = countEl.innerText.trim().match(/^(\\d[\\d,]*)/);
        if (m) return parseInt(m[1].replace(/,/g, ''));
      }
      return 0;
    })()
    """
    r = cdp_eval(ws_url, js)
    return int(r) if isinstance(r, int) else 0


def has_see_more_btn(ws_url: str) -> bool:
    """检查是否存在「查看更多」按钮"""
    js = """
    (function() {
      var btn = document.querySelector('div._3HKY2899[role="link"]');
      if (btn) return true;
      // 降级：aria-label 包含「查看更多」的 button
      var btns = document.querySelectorAll('[aria-label*="查看更多"], [aria-label*="See more"], [aria-label*="see more"]');
      return btns.length > 0;
    })()
    """
    return bool(cdp_eval(ws_url, js))


def click_see_more(ws_url: str) -> bool:
    """点击「查看更多」按钮"""
    js = """
    (function() {
      // 优先点内部 button（aria-label="查看更多商品"）
      var btn = document.querySelector('div[aria-label="查看更多商品"][role="button"]');
      if (!btn) btn = document.querySelector('div._3HKY2899[role="link"]');
      if (!btn) {
        var els = document.querySelectorAll('[aria-label*="查看更多"], [aria-label*="See more"]');
        if (els.length > 0) btn = els[0];
      }
      if (btn) {
        btn.scrollIntoView({block: 'center'});
        btn.click();
        return 'clicked';
      }
      return 'not-found';
    })()
    """
    r = cdp_eval(ws_url, js)
    return str(r) == 'clicked'


def scroll_and_load(ws_url: str, current_count: int, total: int, print_fn=print, max_clicks: int = 30) -> int:
    """点击「查看更多」按钮循环加载，直到全量商品。返回最终加载数量。"""
    prev_count = current_count
    no_change_count = 0

    for i in range(max_clicks):
        if not has_see_more_btn(ws_url):
            break

        click_see_more(ws_url)
        time.sleep(1.5)  # 等待新商品渲染

        count_js = "document.querySelectorAll('div._6q6qVUF5._1UrrHYym').length"
        count = cdp_eval(ws_url, count_js)
        count = count if isinstance(count, int) else prev_count

        if count >= total:
            print_fn(f"  ↳ 已加载 {count}/{total} 件（全量）")
            return count

        if count == prev_count:
            no_change_count += 1
            if no_change_count >= 3:
                break
        else:
            no_change_count = 0
            print_fn(f"  ↳ 已加载 {count}/{total} 件...")

        prev_count = count

    return prev_count


def scrape_items_batch(ws_url: str, offset: int, limit: int = 50) -> list:
    """分批抓取商品（offset 起始索引，limit 每批数量）"""
    js = f"""
    (function() {{
      var results = [];
      var cards = document.querySelectorAll('div._6q6qVUF5._1UrrHYym');
      var start = {offset};
      var end = Math.min(start + {limit}, cards.length);
      for (var i = start; i < end; i++) {{
        var card = cards[i];
        var r = {{}};

        var linkEl = card.querySelector('a[href*="-g-"]');
        r.url = linkEl ? linkEl.href : '';

        r.name = card.getAttribute('data-tooltip-title') || '';
        if (!r.name && linkEl) {{
          r.name = linkEl.innerText.trim()
            .replace(/在新标签页中打开。/g, '').trim().split('\\n')[0];
        }}

        var mainImg = card.querySelector('img[data-js-main-img="true"]')
          || card.querySelector('img[src*="kwcdn.com/product"]');
        r.image = mainImg ? mainImg.src : '';

        var allEls = card.querySelectorAll('*');
        var prices = [];
        for (var j = 0; j < allEls.length; j++) {{
          var el = allEls[j];
          var txt = el.children.length === 0 && el.innerText ? el.innerText.trim() : '';
          if (txt.match(/^[A-Z]{{0,3}}\\$[\\d\\.]+$/) || txt.match(/^[¥€£][\\d,\\.]+$/)) {{
            prices.push(txt);
          }}
        }}
        var unique = prices.filter(function(v, idx, a) {{ return a.indexOf(v) === idx; }});
        r.price = unique[0] || '';
        r.originalPrice = unique[1] || '';

        var soldEl = null;
        var allSoldEls = card.querySelectorAll('._2XgTiMJi');
        for (var j=0; j<allSoldEls.length; j++) {{
          var t = allSoldEls[j].innerText.trim();
          if (t.startsWith('已售') || t.match(/^\\d+.*件$/)) {{ soldEl = allSoldEls[j]; break; }}
        }}
        if (soldEl) {{
          r.sold = soldEl.innerText.trim().replace(/^已售/, '');
        }} else {{
          for (var j = 0; j < allEls.length; j++) {{
            var t = allEls[j].children.length === 0 && allEls[j].innerText
              ? allEls[j].innerText.trim() : '';
            if (t.match(/^[\\d\\.万千,]+件$/) || t.toLowerCase().match(/^[\\d,]+\\s*sold/)) {{
              r.sold = t; break;
            }}
          }}
        }}

        for (var j = 0; j < allEls.length; j++) {{
          var t = allEls[j].children.length === 0 && allEls[j].innerText
            ? allEls[j].innerText.trim() : '';
          if (t.match(/^[1-5]星/) || t.match(/^[1-5]\\s*star/i)) {{
            r.rating = t; break;
          }}
        }}

        var tooltip = card.getAttribute('data-tooltip') || '';
        var m1 = tooltip.match(/goodContainer-(\\d+)/);
        r.goodsId = m1 ? m1[1] : (r.url.match(/g-(\\d+)\\.html/) || ['', ''])[1];

        if (r.name || r.url) results.push(r);
      }}
      return results;
    }})()
    """
    result = cdp_eval(ws_url, js)
    return result if isinstance(result, list) else []


def scrape_items_all(ws_url: str, print_fn=print) -> list:
    """分批抓取所有已加载商品"""
    total_js = "document.querySelectorAll('div._6q6qVUF5._1UrrHYym').length"
    total = cdp_eval(ws_url, total_js)
    total = total if isinstance(total, int) else 0

    all_items = []
    batch = 50
    for offset in range(0, total, batch):
        items = scrape_items_batch(ws_url, offset, batch)
        all_items.extend(items)

    return all_items


def run(mall_url: str = "", output_path: str = None, print_fn=print):
    install_temu_adapters()

    if output_path is None:
        output_path = desktop_path(timestamped_name("temu_store_items"))

    ws_url = get_tab_ws_url(DOMAIN)
    if not ws_url:
        print_fn("❌ 未找到 temu.com 的 tab，请先在 Chrome 中打开店铺页面")
        return None

    if mall_url:
        print_fn("🔍 导航到店铺页面...")
        cdp_navigate(ws_url, mall_url)
        time.sleep(3)

    # 获取商品总数（nav 区域「175 商品」）
    total = get_goods_total(ws_url)
    print_fn(f"📦 共 {total} 件商品，开始加载...")

    # 初始加载数量（首页已渲染的商品卡）
    cur = cdp_eval(ws_url, "document.querySelectorAll('div._6q6qVUF5._1UrrHYym').length")
    cur = cur if isinstance(cur, int) else 0

    # 滚动触发懒加载直到全量
    if total > cur:
        print_fn(f"  当前已加载 {cur} 件，滚动加载剩余...")
        cur = scroll_and_load(ws_url, cur, total, print_fn)
        time.sleep(0.5)
    else:
        print_fn(f"  已加载 {cur} 件")

    print_fn(f"  ✓ 共加载 {cur} 件，开始抓取...")

    headers = ["商品名称", "商品链接", "价格", "原价", "销量", "评分", "商品图片", "goods_id"]
    items = scrape_items_all(ws_url, print_fn)

    if not items:
        print_fn("⚠️ 未抓取到商品数据")
        return None

    rows = [[
        it.get('name', ''),
        it.get('url', ''),
        it.get('price', ''),
        it.get('originalPrice', ''),
        it.get('sold', ''),
        it.get('rating', ''),
        it.get('image', ''),
        it.get('goodsId', ''),
    ] for it in items]

    write_temu_excel(output_path, [{"title": "店铺商品", "headers": headers, "rows": rows}])
    print_fn(f"\n✅ 完成！共 {len(rows)} 条，已保存到:\n   {output_path}")
    return output_path


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Temu 店铺商品抓取")
    parser.add_argument("--url", default="", help="店铺 URL（mall.html?mall_id=xxx）")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    run(mall_url=args.url, output_path=args.output)
