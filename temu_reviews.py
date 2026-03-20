"""
Temu 运营助手 — 店铺评价抓取
页面: https://www.temu.com/mall.html?mall_id=xxx
使用 CDP WebSocket 直连，点击「评价/Reviews」tab 后翻页抓取
字段：用户名、来源国家、购买日期、购买规格、评价内容（翻译版）、原文、星级、评价图片
支持中英文双语页面
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

DOMAIN = "temu.com/mall"

# ─────────────────────────────────────────────
#  JS 片段（全部用原始字符串，避免 Python 转义问题）
# ─────────────────────────────────────────────

_JS_CLICK_HOME = r"""
(function() {
  var navItems = document.querySelectorAll('h2._2kIA1PhC');
  for (var i = 0; i < navItems.length; i++) {
    var t = navItems[i].innerText.trim();
    if (t === '首页' || t === 'Home') { navItems[i].click(); return 'clicked:' + t; }
  }
  return 'not-found';
})()
"""

_JS_CLICK_REVIEWS = r"""
(function() {
  var navItems = document.querySelectorAll('h2._2kIA1PhC');
  for (var i = 0; i < navItems.length; i++) {
    var t = navItems[i].innerText.trim();
    if (t === '评价' || t.toLowerCase() === 'reviews') {
      navItems[i].click();
      return 'clicked:' + t;
    }
  }
  return 'not-found:count=' + navItems.length;
})()
"""

_JS_REVIEW_TOTAL = r"""
(function() {
  var allEls = document.querySelectorAll('*');
  for (var i = 0; i < allEls.length; i++) {
    var txt = allEls[i].children.length === 0 && allEls[i].innerText
      ? allEls[i].innerText.trim() : '';
    var m = txt.match(/^(\d[\d,]*)\s*(评价|条评价|[Rr]eviews?)/);
    if (m) return parseInt(m[1].replace(/,/g, ''));
  }
  return 0;
})()
"""

_JS_COUNT_CARDS = "document.querySelectorAll('div._9WTBQrvq').length"

_JS_FIRST_USER = "var el=document.querySelector('div._9WTBQrvq .XTEkYdlM');el?el.innerText.trim():''"

_JS_HAS_NEXT = r"""
(function() {
  var next = document.querySelector('li.temu-pagination-next');
  if (!next) return false;
  return next.getAttribute('aria-disabled') !== 'true'
    && !next.classList.contains('temu-pagination-disabled');
})()
"""

_JS_CLICK_NEXT = r"""
(function() {
  var next = document.querySelector('li.temu-pagination-next');
  if (next && next.getAttribute('aria-disabled') !== 'true') { next.click(); return true; }
  return false;
})()
"""

_JS_SCRAPE_PAGE = r"""
(function() {
  var results = [];
  var cards = document.querySelectorAll('div._9WTBQrvq');

  for (var i = 0; i < cards.length; i++) {
    var card = cards[i];
    var r = {};

    // ── 用户名
    var nameEl = card.querySelector('.XTEkYdlM');
    r.username = nameEl ? nameEl.innerText.trim() : '';

    // ── 国家 + 购买日期
    // 中文: "来自加拿大 · 2025年11月30日"
    // 英文A: "From Canada · Nov 30, 2025"
    // 英文B: "in Peru on Sep. 24, 2025"  (含 &nbsp;)
    var metaEl = card.querySelector('._1tSRIohB');
    var ariaLabel = metaEl ? (metaEl.getAttribute('aria-label') || '').replace(/\u00a0/g, ' ').trim() : '';
    r.country = '';
    r.purchaseDate = '';
    if (ariaLabel) {
      var enB = ariaLabel.match(/^in\s+(.+?)\s+on\s+(.+)$/i);
      if (enB) {
        r.country = enB[1].trim();
        r.purchaseDate = enB[2].trim();
      } else {
        var cnOrEnA = ariaLabel.match(/(?:来自|From)\s*([^\u00b7\s·]+)/i);
        r.country = cnOrEnA ? cnOrEnA[1].trim() : '';
        var dM = ariaLabel.match(/[\u00b7·]\s*(.+)$/);
        r.purchaseDate = dM ? dM[1].trim() : '';
      }
    }

    // ── 星级
    // 中文: "5星（满分5星）"  英文: "5 out of five stars"
    var starEl = card.querySelector('._7JDNQb0g._1uEtAYnT')
      || card.querySelector('[aria-label*="out of"]')
      || card.querySelector('[aria-label*="stars"]')
      || card.querySelector('[aria-label*="星（满分"]');
    r.stars = '';
    if (starEl) {
      var sl = starEl.getAttribute('aria-label') || '';
      var sm = sl.match(/^([0-9.]+)/) || sl.match(/Rated\s+([0-9.]+)/i);
      if (sm) {
        r.stars = sm[1];
      } else {
        var words = ['one','two','three','four','five'];
        for (var wi = 0; wi < words.length; wi++) {
          if (sl.toLowerCase().indexOf(words[wi]) >= 0) { r.stars = String(wi + 1); break; }
        }
      }
    }

    // ── 购买规格
    // 中文: "购买：xxx / 标签尺寸：yyy"  英文: "Purchased: xxx / Size label: yyy"
    var specEl = card.querySelector('._2QI6iM-X')
      || card.querySelector('._2Y-spytg')
      || card.querySelector('._35Cqvk-G');
    if (!specEl) {
      var allLeaf = card.querySelectorAll('*');
      for (var j = 0; j < allLeaf.length; j++) {
        var lt = allLeaf[j].children.length === 0 && allLeaf[j].innerText
          ? allLeaf[j].innerText.trim() : '';
        if (lt.indexOf('购买：') === 0 || lt.indexOf('Purchased:') === 0
            || lt.indexOf('Color:') === 0 || lt.indexOf('Style:') === 0
            || lt.indexOf('规格：') === 0 || lt.indexOf('Overall fit:') === 0) {
          specEl = allLeaf[j]; break;
        }
      }
    }
    r.spec = specEl ? specEl.innerText.trim() : '';

    // ── 评价正文（翻译版）+ 原文
    var leafTexts = [];
    var allEls = card.querySelectorAll('*');
    for (var j = 0; j < allEls.length; j++) {
      var el = allEls[j];
      var t = el.children.length === 0 && el.innerText ? el.innerText.trim() : '';
      if (t.length <= 10) continue;
      if (t === r.username || t === r.spec) continue;
      if (t.indexOf('购买于') === 0 || t.indexOf('Purchased on') === 0) continue;
      if (t.indexOf('Review before translation:') === 0) { leafTexts.push(t); continue; }
      if (/^[0-9.]+星/.test(t)) continue;
      if (/^[0-9.]+ out of/i.test(t)) continue;
      if (/^Rated [0-9]/i.test(t)) continue;
      if (/^已售/.test(t) || /^Sold\s/i.test(t)) continue;
      leafTexts.push(t);
    }
    var translated = leafTexts.filter(function(x) {
      return x.indexOf('Review before translation:') !== 0;
    });
    r.reviewText = translated.sort(function(a, b) { return b.length - a.length; })[0] || '';
    var origArr = leafTexts.filter(function(x) {
      return x.indexOf('Review before translation:') === 0;
    });
    r.reviewOriginal = origArr[0]
      ? origArr[0].replace('Review before translation:', '').trim() : '';

    // ── 评价图片（排除头像/国旗）
    var imgs = card.querySelectorAll('img');
    var imgUrls = [];
    for (var j = 0; j < imgs.length; j++) {
      var src = imgs[j].src || '';
      if (src && src.indexOf('avatar.') < 0 && src.indexOf('/flags/') < 0
          && src.indexOf('aimg.kwcdn') < 0) {
        imgUrls.push(src);
      }
    }
    r.images = imgUrls.join('|');

    if (r.username || r.reviewText) results.push(r);
  }
  return results;
})()
"""


def _nav_count(ws_url):
    r = cdp_eval(ws_url, "document.querySelectorAll('h2._2kIA1PhC').length")
    return r if isinstance(r, int) else 0


def click_reviews_tab(ws_url: str, wait_timeout: int = 10) -> bool:
    start = time.time()
    while time.time() - start < wait_timeout:
        if _nav_count(ws_url) > 0:
            break
        time.sleep(0.5)
    r = cdp_eval(ws_url, _JS_CLICK_REVIEWS)
    return str(r).startswith('clicked:')


def get_review_total(ws_url: str) -> int:
    r = cdp_eval(ws_url, _JS_REVIEW_TOTAL)
    return int(r) if isinstance(r, (int, float)) else 0


def has_next_page(ws_url: str) -> bool:
    return bool(cdp_eval(ws_url, _JS_HAS_NEXT))


def click_next_page(ws_url: str):
    cdp_eval(ws_url, _JS_CLICK_NEXT)


def wait_for_page_turn(ws_url: str, old_first_user: str, timeout: int = 10) -> bool:
    """等待翻页完成：检测第一条评价的用户名变化。"""
    start = time.time()
    while time.time() - start < timeout:
        time.sleep(0.4)
        new_user = cdp_eval(ws_url, _JS_FIRST_USER)
        if isinstance(new_user, str) and new_user and new_user != old_first_user:
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

    if mall_url:
        print_fn("🔍 导航到店铺页面...")
        cdp_navigate(ws_url, mall_url)
        time.sleep(4)

    # 点「评价」tab，再跳回第1页（Temu 会记住上次翻页位置）
    print_fn("📋 点击「评价」tab...")
    ok = click_reviews_tab(ws_url)
    if not ok:
        print_fn("⚠️ 未找到评价 tab，尝试继续...")
    time.sleep(2.0)

    # 跳到第1页（点分页器第1页按钮）
    _reset_r = cdp_eval(ws_url, r"""
    (function() {
      var p1 = document.querySelector('li.temu-pagination-item-1');
      if (p1) { p1.click(); return 'reset-to-page-1'; }
      return 'no-pager-yet';
    })()
    """)
    if str(_reset_r) == 'reset-to-page-1':
        time.sleep(1.5)  # 等第1页内容加载
    else:
        time.sleep(0.5)

    total = get_review_total(ws_url)
    print_fn(f"  共 {total} 条评价")

    headers = ["用户名", "来源国家", "购买日期", "购买规格", "评价内容", "原文", "星级", "评价图片"]
    all_rows = []
    page = 1

    while True:
        print_fn(f"  正在抓取第 {page} 页...")

        # 记录翻页前的第1条用户名（用于翻页等待检测）
        first_user = cdp_eval(ws_url, _JS_FIRST_USER)
        first_user = first_user if isinstance(first_user, str) else ""

        reviews = cdp_eval(ws_url, _JS_SCRAPE_PAGE)
        if not isinstance(reviews, list):
            reviews = []

        # 0条时最多重试1次
        if len(reviews) == 0 and page > 1:
            time.sleep(1.5)
            reviews = cdp_eval(ws_url, _JS_SCRAPE_PAGE)
            if not isinstance(reviews, list):
                reviews = []

        print_fn(f"  ✓ 第 {page} 页获取 {len(reviews)} 条")

        for rv in reviews:
            all_rows.append([
                rv.get('username', ''),
                rv.get('country', ''),
                rv.get('purchaseDate', ''),
                rv.get('spec', ''),
                rv.get('reviewText', ''),
                rv.get('reviewOriginal', ''),
                rv.get('stars', ''),
                rv.get('images', ''),
            ])

        if not has_next_page(ws_url):
            print_fn("  ↳ 已是最后一页")
            break

        click_next_page(ws_url)
        loaded = wait_for_page_turn(ws_url, first_user, timeout=10)
        if not loaded:
            time.sleep(1.5)  # fallback
        page += 1

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
