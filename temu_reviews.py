"""
Temu 运营助手 — 店铺评价抓取
页面: https://www.temu.com/mall.html?mall_id=xxx
使用 CDP WebSocket 直连，点击「评价/Reviews」tab 后翻页抓取
字段：用户名、来源国家、购买日期、购买规格、评价内容（翻译版）、原文、星级、评价图片
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


def click_reviews_tab(ws_url: str, wait_timeout: int = 10) -> bool:
    """等待 nav 渲染完成后点击「评价/Reviews」tab"""
    # 先等待 nav 元素出现
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
        if (txt === '评价' || txt === 'Reviews' || txt.toLowerCase().startsWith('review')) {
          navItems[i].click();
          return 'clicked:' + txt;
        }
      }
      return 'not-found:count=' + navItems.length;
    })()
    """
    r = cdp_eval(ws_url, js)
    return str(r).startswith('clicked:')


def get_review_total(ws_url: str) -> int:
    js = """
    (function() {
      var allEls = document.querySelectorAll('*');
      for (var i = 0; i < allEls.length; i++) {
        var txt = allEls[i].children.length === 0 && allEls[i].innerText
          ? allEls[i].innerText.trim() : '';
        var m = txt.match(/^(\\d[\\d,]*)\\s*(评价|条评价|Reviews?|review)/i);
        if (m) return parseInt(m[1].replace(/,/g, ''));
      }
      return 0;
    })()
    """
    r = cdp_eval(ws_url, js)
    return int(r) if isinstance(r, (int, float)) else 0


def scrape_reviews_page(ws_url: str) -> list:
    """抓取当前页所有评价条目。真实容器是 div._9WTBQrvq，包含：
    - div._3OHJMKy5 > div._3t3Ev35j（用户名+日期）
    - div._21WXPU_9（星级+规格+正文+图片）
    """
    js = """
    (function() {
      var results = [];
      // 每条评价的根容器
      var cards = document.querySelectorAll('div._9WTBQrvq');

      for (var i = 0; i < cards.length; i++) {
        var card = cards[i];
        var r = {};

        // ── 用户名 ──────────────────────────
        var nameEl = card.querySelector('.XTEkYdlM');
        r.username = nameEl ? nameEl.innerText.trim() : '';

// ── 国家 + 购买日期（aria-label 支持中英双语）──────────────────
        // 中文: "来自加拿大 · 2025年11月30日"
        // 英文: "in Peru on Sep. 24, 2025"（"in"和国名之间可能是 &nbsp;）
        var metaEl = card.querySelector('._1tSRIohB');
        var ariaLabel = metaEl ? (metaEl.getAttribute('aria-label') || '') : '';
        r.country = ''; r.purchaseDate = '';
        if (ariaLabel) {
          // 英文格式：「in <Country> on <Date>」
          var enM = ariaLabel.replace(/\\u00a0/g, ' ').match(/^in\\s+(.+?)\\s+on\\s+(.+)$/i);
          if (enM) {
            r.country = enM[1].trim();
            r.purchaseDate = enM[2].trim();
          } else {
            // 中文格式：「来自XXX · 日期」
            var cnM = ariaLabel.match(/(?:来自|From)\\s*([^·\\s]+)/) || ariaLabel.match(/^([^·]+?)(?:\\s*·|$)/);
            r.country = cnM ? cnM[1].trim() : '';
            var dM = ariaLabel.match(/·\\s*(.+)$/);
            r.purchaseDate = dM ? dM[1].trim()
              : (metaEl ? metaEl.innerText.replace(/购买于/g,'').trim().replace(/[in\\s·]/g,'').trim() : '');
          }
        }
        // ── 星级（中英文兼容）
        // 中文: "5星（满分5星）" | 英文: "5 out of 5 stars" / "Rated 5 out of 5"
        var starEl = card.querySelector('._7JDNQb0g._1uEtAYnT, [class*="_7JDNQb0g"][aria-label]');
        if (!starEl) starEl = card.querySelector('[aria-label*="星（满分"], [aria-label*="out of"], [aria-label*="stars"]');
        if (starEl) {
          var starLabel = starEl.getAttribute('aria-label') || '';
          // "5星（满分5星）" / "5 out of five stars" / "Rated 5 out of 5"
          var sm = starLabel.match(/^([0-9.]+)/) || starLabel.match(/Rated\\s+([0-9.]+)/i);
          if (!sm) { var m5 = ['one','two','three','four','five']; var idx = -1;
            for (var mi=0; mi<m5.length; mi++) { if (starLabel.toLowerCase().includes(m5[mi])) { idx=mi+1; break; } }
            if (idx > 0) sm = [null, String(idx)]; }
          r.stars = sm ? sm[1] : starLabel;
        } else {
          r.stars = '';
        }

        // ── 购买规格（中英文兼容）
        // 中文: 「购买：咖啡50892 / 标签尺寸：120」
        // 英文: 「Purchased: Brown50892 / Size label: 120」
        var specEl = card.querySelector('._2QI6iM-X, ._2Y-spytg, ._35Cqvk-G');
        if (!specEl) {
          var allLeaf = card.querySelectorAll('*');
          for (var j=0; j<allLeaf.length; j++) {
            var lt = allLeaf[j].children.length===0 && allLeaf[j].innerText
              ? allLeaf[j].innerText.trim() : '';
            if (lt.startsWith('购买：') || lt.startsWith('Purchased:')
                || lt.startsWith('Color:') || lt.startsWith('Size:')
                || lt.startsWith('规格：') || lt.startsWith('Style:')
                || lt.startsWith('Overall fit:') || lt.startsWith('Size:')) {
              specEl = allLeaf[j]; break;
            }
          }
        }
        r.spec = specEl ? specEl.innerText.trim() : '';

        // ── 评价正文（翻译版）────────────────────────────────────────────
        var leafTexts = [];
        var allEls = card.querySelectorAll('*');
        for (var j=0; j<allEls.length; j++) {
          var el = allEls[j];
          var t = el.children.length===0 && el.innerText ? el.innerText.trim() : '';
          if (t.length > 10
            && t !== r.username
            && t !== r.spec
            && !t.startsWith('购买于')
            && !t.startsWith('Purchased on')
            && !t.startsWith('Review before translation:')
            && !t.match(/^[0-9.]+星/)
            && !t.match(/^[0-9.]+ out of/i)
            && !t.match(/^Rated [0-9]/i)
            && !t.match(/^已售/)
            && !t.match(/^Sold/)
            && !t.match(/^on [A-Z][a-z]+\\\./)
          ) {
            leafTexts.push(t);
          }
        }
        // 翻译版是中文（或本地语言），原文以「Review before translation:」开头
        var translated = leafTexts.filter(function(t) {
          return !t.includes('Review before translation');
        });
        r.reviewText = translated.sort(function(a,b){return b.length-a.length;})[0] || '';

        // 原文
        var origTexts = leafTexts.filter(function(t) {
          return t.startsWith('Review before translation:');
        });
        r.reviewOriginal = origTexts[0]
          ? origTexts[0].replace('Review before translation:', '').trim() : '';

        // ── 评价图片（排除头像和国旗）────────────────────────────────────
        var imgs = card.querySelectorAll('img');
        var imgUrls = [];
        for (var j=0; j<imgs.length; j++) {
          var src = imgs[j].src || '';
          // 排除头像（avatar.kwcdn）和国旗（upload_aimg/openingemail/flags）
          if (src
            && !src.includes('avatar.')
            && !src.includes('/flags/')
            && !src.includes('aimg.kwcdn')
          ) {
            imgUrls.push(src);
          }
        }
        r.images = imgUrls.join('|');

        if (r.username || r.reviewText) results.push(r);
      }
      return results;
    })()
    """
    result = cdp_eval(ws_url, js)
    return result if isinstance(result, list) else []


def has_next_page(ws_url: str) -> bool:
    js = """
    (function() {
      var next = document.querySelector('li.temu-pagination-next');
      if (!next) return false;
      return next.getAttribute('aria-disabled') !== 'true'
        && !next.classList.contains('temu-pagination-disabled');
    })()
    """
    return bool(cdp_eval(ws_url, js))


def click_next_page(ws_url: str):
    js = """
    (function() {
      var next = document.querySelector('li.temu-pagination-next');
      if (next && next.getAttribute('aria-disabled') !== 'true') { next.click(); return true; }
      return false;
    })()
    """
    cdp_eval(ws_url, js)


def wait_reviews_load(ws_url: str, old_count: int, timeout: int = 12, old_first_user: str = "") -> bool:
    """等待新评价加载。支持两种场景:
    1. 卡片数量变化（新页卡片数不同于旧页，如最后一页少于10条）
    2. 卡片数量不变但内容变化（每页都是10条时通过第一条用户名变化检测）
    """
    start = time.time()
    while time.time() - start < timeout:
        time.sleep(0.5)
        count = cdp_eval(ws_url, "document.querySelectorAll('div._9WTBQrvq').length")
        if isinstance(count, int) and count > 0 and count != old_count:
            time.sleep(0.3)
            return True
        # 检测内容变化（第一条评价的用户名）
        if old_first_user:
            first_user = cdp_eval(ws_url,
                "var el=document.querySelector('div._9WTBQrvq .XTEkYdlM'); el ? el.innerText.trim() : ''")
            if isinstance(first_user, str) and first_user and first_user != old_first_user:
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

    if mall_url:
        print_fn("🔍 导航到店铺页面...")
        cdp_navigate(ws_url, mall_url)
        time.sleep(4)  # 等页面完整加载（nav 渲染需要时间）

    # 点击「评价」tab
    print_fn("📋 点击「评价」tab...")
    ok = click_reviews_tab(ws_url)
    if not ok:
        print_fn("⚠️ 未找到评价 tab，尝试继续...")
    time.sleep(2.5)

    # 先点「首页/Home」tab 再点「评价/Reviews」tab，确保评价列表从第1页开始
    _reset_js = '''
    (function() {
      var navItems = document.querySelectorAll('h2._2kIA1PhC');
      for (var i=0; i<navItems.length; i++) {
        var t = navItems[i].innerText.trim();
        if (t==='首页' || t==='Home') { navItems[i].click(); return 'clicked:'+t; }
      }
      return 'not-found';
    })()
    '''
    cdp_eval(ws_url, _reset_js)
    time.sleep(1.5)
    click_reviews_tab(ws_url)
    time.sleep(1.5)

    total = get_review_total(ws_url)
    print_fn(f"  共 {total} 条评价")

    headers = ["用户名", "来源国家", "购买日期", "购买规格", "评价内容", "原文", "星级", "评价图片"]
    all_rows = []
    page = 1

    while True:
        print_fn(f"  正在抓取第 {page} 页...")
        old_count = cdp_eval(ws_url, "document.querySelectorAll('div._9WTBQrvq').length")
        old_first_user = cdp_eval(ws_url,
            "var el=document.querySelector('div._9WTBQrvq .XTEkYdlM'); el ? el.innerText.trim() : ''")
        old_first_user = old_first_user if isinstance(old_first_user, str) else ""
        reviews = scrape_reviews_page(ws_url)

        # 如果 0 条，可能还未渲染完，等待后重试一次
        if len(reviews) == 0 and page > 1:
            time.sleep(1.5)
            reviews = scrape_reviews_page(ws_url)

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
        # 等待新内容加载：优先用内容变化检测，最少等1.5s
        loaded = wait_reviews_load(ws_url, old_count if isinstance(old_count, int) else 0, old_first_user=old_first_user)
        if not loaded:
            time.sleep(1.5)  # fallback：超时时至少再等一下
        page += 1
        time.sleep(0.3)

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
