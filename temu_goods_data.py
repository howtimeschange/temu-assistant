"""
Temu 运营助手 — 商品数据抓取
页面: https://agentseller.temu.com/newon/goods-data
使用 CDP WebSocket 直接执行 JS，读取 Beast 组件库的表格数据
"""
import sys
import os
import time
import json
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))
from src.temu_utils import (
    install_temu_adapters, desktop_path, timestamped_name,
    cdp_eval, cdp_navigate, get_tab_ws_url
)
from src.temu_excel import write_temu_excel

GOODS_URL = "https://agentseller.temu.com/newon/goods-data"
DOMAIN    = "agentseller.temu.com"


def scrape_page(ws_url: str, print_fn=print) -> list:
    """用 CDP eval 抓取当前页的表格数据"""
    js = """
    (function() {
      var results = [];
      var rows = document.querySelectorAll('tbody tr.TB_tr_5-120-1');
      for (var ri = 0; ri < rows.length; ri++) {
        var row = rows[ri];
        // 跳过 checkbox 列（TB_checkCell），从普通 td 开始
        var tds = row.querySelectorAll('td.TB_td_5-120-1:not(.TB_checkCell_5-120-1)');
        if (tds.length < 3) continue;

        // tds[0] = 商品信息（商品名、分类、SPU、SKC）
        var infoText = tds[0].innerText.trim();
        var lines = infoText.split('\\n').map(function(s){ return s.trim(); }).filter(Boolean);
        var goodsName = '', category = '', spu = '', skc = '';
        for (var i = 0; i < lines.length; i++) {
          if (lines[i] === 'SPU：') { spu = lines[i+1] || ''; i++; }
          else if (lines[i] === 'SKC：') { skc = lines[i+1] || ''; i++; }
          else if (!goodsName) goodsName = lines[i];
          else if (!category) category = lines[i];
        }

        // tds[1] = 国家/地区
        var country = tds[1] ? tds[1].innerText.trim() : '';

        // tds[2] = 支付件数 + 趋势
        var payText = tds[2] ? tds[2].innerText.trim() : '';
        var payLines = payText.split('\\n').map(function(s){ return s.trim(); }).filter(Boolean);
        var payCount = payLines[0] || '';
        var trend = payLines[1] || '';

        if (goodsName || spu) {
          results.push([goodsName, category, spu, skc, country, payCount, trend]);
        }
      }
      return results;
    })()
    """
    result = cdp_eval(ws_url, js)
    if isinstance(result, list):
        return result
    return []


def get_total_pages(ws_url: str) -> int:
    """获取总页数"""
    js = """
    (function() {
      var totalEl = document.querySelector('.PGT_totalText_5-120-1');
      if (!totalEl) return {total: 0, pages: 1};
      var m = totalEl.textContent.match(/(\\d+)/);
      var total = m ? parseInt(m[1]) : 0;
      var nextBtn = document.querySelector('.PGT_next_5-120-1');
      var lastPageEl = document.querySelector('.PGT_outerWrapper_5-120-1 li.PGT_pagerItem_5-120-1:last-of-type');
      var lastPage = lastPageEl ? parseInt(lastPageEl.textContent.trim()) : 1;
      return {total: total, lastPage: lastPage};
    })()
    """
    result = cdp_eval(ws_url, js)
    if isinstance(result, dict):
        return result.get('lastPage', 1)
    return 1


def has_next_page(ws_url: str) -> bool:
    js = """
    (function() {
      var next = document.querySelector('.PGT_next_5-120-1');
      return next && !next.classList.contains('PGT_disabled_5-120-1');
    })()
    """
    return bool(cdp_eval(ws_url, js))


def click_next_page(ws_url: str) -> bool:
    js = """
    (function() {
      var next = document.querySelector('.PGT_next_5-120-1');
      if (next && !next.classList.contains('PGT_disabled_5-120-1')) {
        next.click(); return true;
      }
      return false;
    })()
    """
    return bool(cdp_eval(ws_url, js))


def wait_table_load(ws_url: str, old_count: int, timeout: int = 8) -> bool:
    """等待表格重新加载（行数变化 or loading 消失）"""
    start = time.time()
    while time.time() - start < timeout:
        time.sleep(0.5)
        js = "document.querySelectorAll('tbody tr.TB_tr_5-120-1').length"
        count = cdp_eval(ws_url, js)
        if isinstance(count, int) and count != old_count:
            time.sleep(0.3)
            return True
    return False


def set_time_filter(ws_url: str, option_text: str, print_fn=print) -> bool:
    """设置时间区间下拉选择（如：近7天/近30天/近90天）"""
    # 点击时间区间 Select
    js = """
    (function() {
      var labels = document.querySelectorAll('*');
      for (var i = 0; i < labels.length; i++) {
        if (labels[i].children.length === 0 && labels[i].textContent.trim() === '时间区间') {
          var field = labels[i].nextElementSibling;
          if (field) {
            var sel = field.querySelector('[data-testid="beast-core-select"]');
            if (sel) { sel.click(); return 'clicked'; }
          }
        }
      }
      return 'not-found';
    })()
    """
    r = cdp_eval(ws_url, js)
    if r != 'clicked':
        return False

    time.sleep(0.5)

    # 找并点击选项
    js2 = f"""
    (function() {{
      var opts = document.querySelectorAll('[data-testid="beast-core-select-option"], [class*="ST_option"]');
      for (var i = 0; i < opts.length; i++) {{
        if (opts[i].textContent.trim().indexOf('{option_text}') >= 0) {{
          opts[i].click();
          return 'selected:' + opts[i].textContent.trim();
        }}
      }}
      var available = [];
      for (var i = 0; i < opts.length; i++) available.push(opts[i].textContent.trim());
      return 'not-found:' + available.join(',');
    }})()
    """
    r2 = cdp_eval(ws_url, js2)
    print_fn(f"  时间筛选: {r2}")
    return str(r2).startswith('selected:')


def run(mode: str = "current", time_range: str = "", start_date: str = "", end_date: str = "",
        output_path: str = None, login_wait: int = 40, print_fn=print):
    """
    time_range: 预设时间区间，可选值: '近7天' / '近30天' / '近90天'
                留空则使用当前页面默认值。
                注意：Temu 商品数据页的时间筛选是下拉选择，不支持自由日期输入。
    """
    install_temu_adapters()

    if output_path is None:
        output_path = desktop_path(timestamped_name("temu_goods_data"))

    # 获取 tab ws url
    ws_url = get_tab_ws_url(DOMAIN)
    if not ws_url:
        print_fn(f"❌ 未找到 {DOMAIN} 的 tab，请先在 Chrome 中打开 Temu 运营后台")
        return None

    # 导航到商品数据页
    print_fn(f"🔍 导航到商品数据页面...")
    cdp_navigate(ws_url, GOODS_URL)
    time.sleep(3)

    # 等待表格出现
    print_fn("⏳ 等待页面加载...")
    t0 = time.time()
    count = 0
    while time.time() - t0 < 15:
        js = "document.querySelectorAll('tbody tr.TB_tr_5-120-1').length"
        count = cdp_eval(ws_url, js)
        if isinstance(count, int) and count > 0:
            break
        time.sleep(1)
    print_fn(f"  页面已加载，检测到 {count} 行数据")

    # 设置时间区间（近7天/近30天/近90天）
    if time_range:
        print_fn(f"📅 设置时间区间：{time_range}")
        ok = set_time_filter(ws_url, time_range, print_fn)
        if ok:
            # 点查询按钮刷新
            time.sleep(0.5)
            js_query = """
            (function(){
              var btns = document.querySelectorAll('button');
              for (var i=0; i<btns.length; i++){
                if (btns[i].textContent.trim() === '查询') { btns[i].click(); return true; }
              }
              return false;
            })()
            """
            cdp_eval(ws_url, js_query)
            time.sleep(2)
            # 等待表格刷新
            old_count = count
            wait_table_load(ws_url, old_count if isinstance(old_count, int) else 0)
            count = cdp_eval(ws_url, "document.querySelectorAll('tbody tr.TB_tr_5-120-1').length")
            print_fn(f"  ✓ 筛选后检测到 {count} 行数据")
        else:
            print_fn(f"  ⚠️ 未找到「{time_range}」选项，可用值：近7天 / 近30天 / 近90天")
    else:
        # 没有指定时间区间，直接点查询刷新当前数据
        js_query = """
        (function(){
          var btns = document.querySelectorAll('button');
          for (var i=0; i<btns.length; i++){
            if (btns[i].textContent.trim() === '查询') { btns[i].click(); return true; }
          }
          return false;
        })()
        """
        cdp_eval(ws_url, js_query)
        time.sleep(2)

    # 开始抓取所有页
    print_fn("🚀 开始抓取商品数据...")
    headers = ["商品名称", "商品分类", "SPU", "SKC", "国家/地区", "支付件数", "销售趋势"]
    all_rows = []
    page = 1

    while True:
        old_count = len(all_rows)
        print_fn(f"  正在抓取第 {page} 页...")
        rows = scrape_page(ws_url, print_fn)
        all_rows.extend(rows)
        print_fn(f"  ✓ 第 {page} 页获取 {len(rows)} 条")

        if len(rows) == 0:
            print_fn("  ⚠️ 本页无数据，停止")
            break

        if not has_next_page(ws_url):
            print_fn("  ↳ 已是最后一页")
            break

        # 翻页
        cur_count = cdp_eval(ws_url, "document.querySelectorAll('tbody tr.TB_tr_5-120-1').length")
        click_next_page(ws_url)
        wait_table_load(ws_url, cur_count if isinstance(cur_count, int) else 0)
        page += 1
        time.sleep(0.5)

    if not all_rows:
        print_fn("⚠️  未抓取到任何数据，请检查页面状态")
        return None

    write_temu_excel(output_path, [{"title": "商品数据", "headers": headers, "rows": all_rows}])
    print_fn(f"\n✅ 完成！共 {len(all_rows)} 条，已保存到:\n   {output_path}")
    return output_path


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Temu 商品数据抓取")
    parser.add_argument("--mode", choices=["current", "new"], default="current")
    parser.add_argument("--time-range", default="",
                        help="时间区间预设：近7天 / 近30天 / 近90天（留空使用页面默认值）")
    parser.add_argument("--output", default=None)
    parser.add_argument("--wait",  type=int, default=40)
    args = parser.parse_args()
    run(mode=args.mode, time_range=args.time_range,
        output_path=args.output, login_wait=args.wait)
