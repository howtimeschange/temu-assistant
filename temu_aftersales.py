"""
Temu 运营助手 — 售后数据抓取
页面: https://agentseller.temu.com/main/aftersales/information
支持地区: 全球 / 美国 / 欧区
使用 CDP WebSocket 直连，自动翻页抓取全量数据
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

DOMAIN = "agentseller"  # 匹配 agentseller.temu.com 和 agentseller-us.temu.com 等子域名
AFTERSALES_URL = "https://agentseller.temu.com/main/aftersales/information"

HEADERS = ["序号", "单号", "货品SKU ID", "商品名称", "品质分", "售后问题处理倍数",
           "消费者售后申请原因", "消费者售后申请时间"]


def get_regions(ws_url: str) -> list:
    """获取可用地区列表（排除 disabled）"""
    js = """
    (function() {
      var items = document.querySelectorAll('a.index-module__drItem___3eLtO');
      return Array.from(items)
        .filter(function(a) { return !a.classList.contains('index-module__disabled___3n06o'); })
        .map(function(a) {
          return {
            text: a.innerText.trim(),
            active: a.classList.contains('index-module__active___2QJPF')
          };
        });
    })()
    """
    result = cdp_eval(ws_url, js)
    if isinstance(result, list):
        return result
    return []


def switch_region(ws_url: str, region_text: str) -> bool:
    """点击切换地区"""
    js = f"""
    (function() {{
      var items = document.querySelectorAll('a.index-module__drItem___3eLtO');
      for (var i = 0; i < items.length; i++) {{
        if (items[i].innerText.trim() === '{region_text}' &&
            !items[i].classList.contains('index-module__disabled___3n06o')) {{
          items[i].click();
          return 'clicked:' + items[i].innerText.trim();
        }}
      }}
      return 'not-found';
    }})()
    """
    r = cdp_eval(ws_url, js)
    return str(r).startswith('clicked:')


def get_total(ws_url: str) -> int:
    """获取总条数"""
    js = """
    (function() {
      var el = document.querySelector('.PGT_totalText_5-120-1');
      if (!el) return 0;
      var m = el.innerText.match(/\\d+/);
      return m ? parseInt(m[0]) : 0;
    })()
    """
    r = cdp_eval(ws_url, js)
    return int(r) if isinstance(r, int) else 0


def scrape_page(ws_url: str) -> list:
    """抓取当前页所有数据行"""
    js = """
    (function() {
      var results = [];
      // 数据行：包含 td 的 tr（排除表头 tr，表头包含 th）
      var allRows = document.querySelectorAll('tr.TB_tr_5-120-1');
      var dataRows = Array.from(allRows).filter(function(row) {
        return row.querySelector('td') !== null;
      });

      for (var i = 0; i < dataRows.length; i++) {
        var tds = dataRows[i].querySelectorAll('td.TB_td_5-120-1');
        var cells = Array.from(tds).map(function(td) { return td.innerText.trim(); });
        if (cells.length > 0) results.push(cells);
      }
      return results;
    })()
    """
    result = cdp_eval(ws_url, js)
    return result if isinstance(result, list) else []


def has_next_page(ws_url: str) -> bool:
    js = """
    (function() {
      var next = document.querySelector('li.PGT_next_5-120-1');
      if (!next) return false;
      return !next.classList.contains('PGT_disabled_5-120-1');
    })()
    """
    return bool(cdp_eval(ws_url, js))


def click_next_page(ws_url: str):
    js = """
    (function() {
      var next = document.querySelector('li.PGT_next_5-120-1');
      if (next && !next.classList.contains('PGT_disabled_5-120-1')) {
        next.click(); return true;
      }
      return false;
    })()
    """
    cdp_eval(ws_url, js)


def wait_page_change(ws_url: str, old_first_cell: str, timeout: int = 10) -> bool:
    """等待翻页完成（检测第一行第一列变化）"""
    start = time.time()
    while time.time() - start < timeout:
        time.sleep(0.5)
        js = """
        (function() {
          var allRows = document.querySelectorAll('tr.TB_tr_5-120-1');
          var dataRows = Array.from(allRows).filter(function(r) { return r.querySelector('td') !== null; });
          if (dataRows.length === 0) return '';
          var td = dataRows[0].querySelector('td.TB_td_5-120-1');
          return td ? td.innerText.trim() : '';
        })()
        """
        cur = cdp_eval(ws_url, js)
        if str(cur) != str(old_first_cell):
            time.sleep(0.3)
            return True
    return False


def scrape_region(ws_url: str, region_name: str, print_fn) -> list:
    """抓取某地区全量数据"""
    total = get_total(ws_url)
    print_fn(f"  📊 {region_name}：共 {total} 条")
    if total == 0:
        return []

    all_rows = []
    page = 1

    while True:
        print_fn(f"    正在抓取第 {page} 页...")
        # 获取当前第一行第一单元格，用于检测翻页
        js_first = """
        (function() {
          var allRows = document.querySelectorAll('tr.TB_tr_5-120-1');
          var dataRows = Array.from(allRows).filter(function(r) { return r.querySelector('td') !== null; });
          if (dataRows.length === 0) return '';
          var td = dataRows[0].querySelector('td.TB_td_5-120-1');
          return td ? td.innerText.trim() : '';
        })()
        """
        first_cell = cdp_eval(ws_url, js_first)

        rows = scrape_page(ws_url)
        print_fn(f"    ✓ 第 {page} 页获取 {len(rows)} 条")
        all_rows.extend(rows)

        if not has_next_page(ws_url):
            print_fn(f"    ↳ 已是最后一页")
            break

        click_next_page(ws_url)
        wait_page_change(ws_url, first_cell)
        page += 1
        time.sleep(0.3)

    return all_rows


def run(regions: list = None, output_path: str = None, print_fn=print):
    """
    regions: ['全球', '美国', '欧区'] 或 None（抓所有可用地区）
    """
    install_temu_adapters()

    if output_path is None:
        output_path = desktop_path(timestamped_name("temu_aftersales"))

    ws_url = get_tab_ws_url(DOMAIN)
    if not ws_url:
        print_fn("❌ 未找到 agentseller.temu.com 的 tab，请先在 Chrome 中打开售后页面")
        return None

    # 确保在售后页面
    print_fn("🔍 导航到售后信息页面...")
    cdp_navigate(ws_url, AFTERSALES_URL)
    time.sleep(3)

    # 获取可用地区
    available = get_regions(ws_url)
    available_names = [r['text'] for r in available]
    print_fn(f"📋 可用地区：{available_names}")

    if regions is None:
        target_regions = available_names
    else:
        target_regions = [r for r in regions if r in available_names]

    if not target_regions:
        print_fn("⚠️ 没有可用的地区")
        return None

    # 每个地区抓一个 sheet
    sheets = []
    for region in target_regions:
        print_fn(f"\n🌍 切换到：{region}")
        ok = switch_region(ws_url, region)
        if not ok:
            print_fn(f"  ⚠️ 切换 {region} 失败，跳过")
            continue
        time.sleep(2)  # 等待数据刷新

        rows = scrape_region(ws_url, region, print_fn)
        if rows:
            sheets.append({
                "title": region,
                "headers": HEADERS,
                "rows": rows
            })

    if not sheets:
        print_fn("⚠️ 未抓取到任何数据")
        return None

    write_temu_excel(output_path, sheets)
    total = sum(len(s['rows']) for s in sheets)
    print_fn(f"\n✅ 完成！共 {total} 条（{len(sheets)} 个地区），已保存到:\n   {output_path}")
    return output_path


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Temu 售后数据抓取")
    parser.add_argument("--regions", nargs="+", default=None,
                        help="指定地区（全球 美国 欧区），默认全部")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    run(regions=args.regions, output_path=args.output)
