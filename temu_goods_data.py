"""
Temu 运营助手 — 商品数据抓取
页面: https://agentseller.temu.com/newon/goods-data
使用 CDP WebSocket 直接执行 JS，读取 Beast 组件库的表格数据

时间筛选可选值:
  time_range: '昨日' / '近7日' / '近30日'（下拉预设）
              '自定义'（需配合 start_date + end_date）
  start_date/end_date: 'YYYY-MM-DD' 格式，仅在 time_range='自定义' 时生效
"""
import sys
import os
import time
import json

sys.path.insert(0, os.path.dirname(__file__))
from src.temu_utils import (
    install_temu_adapters, desktop_path, timestamped_name,
    cdp_eval, cdp_navigate, get_tab_ws_url, cdp_open_new_tab, CDP_PORT
)
from src.temu_excel import write_temu_excel

GOODS_URL = "https://agentseller.temu.com/newon/goods-data"
DOMAIN    = "agentseller.temu.com"

# 页面实际选项文字映射（兼容用户输入的多种写法 → 页面真实文字）
TIME_RANGE_ALIASES = {
    "昨日": "昨日",
    "昨天": "昨日",
    "近7日": "近7日",
    "近7天": "近7日",
    "近7d": "近7日",
    "近30日": "近30日",
    "近30天": "近30日",
    "近30d": "近30日",
    "自定义": "自定义",
    "custom": "自定义",
}


def scrape_page(ws_url: str, print_fn=print) -> list:
    """用 CDP eval 抓取当前页的表格数据"""
    js = """
    (function() {
      var results = [];
      var rows = document.querySelectorAll('tbody tr.TB_tr_5-120-1');
      for (var ri = 0; ri < rows.length; ri++) {
        var row = rows[ri];
        var tds = row.querySelectorAll('td.TB_td_5-120-1:not(.TB_checkCell_5-120-1)');
        if (tds.length < 3) continue;

        var infoText = tds[0].innerText.trim();
        var lines = infoText.split('\\n').map(function(s){ return s.trim(); }).filter(Boolean);
        var goodsName = '', category = '', spu = '', skc = '';
        for (var i = 0; i < lines.length; i++) {
          if (lines[i] === 'SPU：') { spu = lines[i+1] || ''; i++; }
          else if (lines[i] === 'SKC：') { skc = lines[i+1] || ''; i++; }
          else if (!goodsName) goodsName = lines[i];
          else if (!category) category = lines[i];
        }

        var country = tds[1] ? tds[1].innerText.trim() : '';

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


def get_page_signature(ws_url: str) -> str:
    """获取当前页内容签名，用于判断翻页是否成功"""
    js = """
    (function() {
      var rows = document.querySelectorAll('tbody tr.TB_tr_5-120-1');
      if (rows.length === 0) return '';
      var first = rows[0].innerText.trim().slice(0, 50);
      var last = rows[rows.length - 1].innerText.trim().slice(0, 50);
      return first + '|||' + last + '|||' + rows.length;
    })()
    """
    result = cdp_eval(ws_url, js)
    return str(result) if result else ''


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


def wait_page_change(ws_url: str, old_signature: str, timeout: int = 10) -> bool:
    """等待页面内容真正变化（内容签名对比，避免行数相同误判）"""
    start = time.time()
    while time.time() - start < timeout:
        time.sleep(0.4)
        sig = get_page_signature(ws_url)
        if sig and sig != old_signature:
            time.sleep(0.2)
            return True
    return False


# ── 时间筛选核心逻辑 ──────────────────────────────────────────────────────────

def _open_time_range_dropdown(ws_url: str, print_fn=print) -> bool:
    """点开时间区间下拉，返回是否成功"""
    js = """
    (function() {
      // 找「时间区间」label 旁边的 select trigger
      var all = document.querySelectorAll('*');
      for (var i = 0; i < all.length; i++) {
        var el = all[i];
        if (el.children.length === 0 && el.textContent.trim() === '时间区间') {
          var parent = el.parentElement;
          for (var d = 0; d < 6 && parent; d++) {
            // Beast select: [class*="ST_selector"] 或 [class*="Select"]
            var trigger = parent.querySelector(
              '[class*="ST_selector_"], [class*="ST_selector"], [class*="SLT_selector"]'
            );
            if (trigger) { trigger.click(); return 'ok:ST_selector'; }
            // 兜底：找带下拉箭头 class 的任意 div/span
            var arr = parent.querySelector('[class*="arrow"], [class*="Arrow"], [class*="suffix"]');
            if (arr) { arr.parentElement.click(); return 'ok:arrow'; }
            parent = parent.parentElement;
          }
        }
      }
      // 最后兜底：页面上第一个带 ST_selector class 的元素
      var fb = document.querySelector('[class*="ST_selector_"], [class*="ST_selector"]');
      if (fb) { fb.click(); return 'ok:fallback'; }
      return 'not-found';
    })()
    """
    r = cdp_eval(ws_url, js)
    print_fn(f"  打开下拉: {r}")
    return str(r).startswith('ok:')


def _click_option(ws_url: str, option_text: str, print_fn=print) -> bool:
    """在已展开的下拉中点击指定选项"""
    js = f"""
    (function() {{
      // Beast Select 选项 class 关键词
      var selectors = [
        '[class*="ST_option_"]',
        '[class*="ST_item_"]',
        '[class*="SLT_option"]',
        '[class*="Select_option"]',
        '[role="option"]',
        'li[class*="option"]',
      ];
      for (var si = 0; si < selectors.length; si++) {{
        var opts = document.querySelectorAll(selectors[si]);
        if (!opts.length) continue;
        for (var i = 0; i < opts.length; i++) {{
          var text = opts[i].textContent.trim();
          if (text === '{option_text}') {{
            opts[i].click();
            return 'selected:' + text;
          }}
        }}
        // 收集调试信息
        var avail = [];
        for (var i = 0; i < opts.length; i++) avail.push(opts[i].textContent.trim());
        if (avail.length) return 'not-found[' + selectors[si] + ']:' + avail.join(',');
      }}
      return 'no-options';
    }})()
    """
    r = cdp_eval(ws_url, js)
    print_fn(f"  选项点击: {r}")
    return str(r).startswith('selected:')


def set_preset_time_filter(ws_url: str, option_text: str, print_fn=print) -> bool:
    """
    设置预设时间区间（昨日/近7日/近30日）。
    流程：点击下拉 trigger → 等待选项展开 → 点击目标选项。
    """
    # 规范化选项文字
    real_option = TIME_RANGE_ALIASES.get(option_text, option_text)
    print_fn(f"  目标选项: 「{real_option}」")

    if not _open_time_range_dropdown(ws_url, print_fn):
        return False

    time.sleep(0.5)
    return _click_option(ws_url, real_option, print_fn)


def _get_rpr_panel_selector():
    """返回 Beast RPR 日历弹窗的 JS 选择表达式（变量名 pp）"""
    # 日历弹窗有多个 PP_outerWrapper，用含 RPR_outerPickerWrapper 的那个
    return """
    var panels = document.querySelectorAll('[class*="PP_outerWrapper"]');
    var pp = null;
    for(var _i=0;_i<panels.length;_i++){
      if(panels[_i].querySelector('[class*="RPR_outerPickerWrapper"]')){
        pp = panels[_i]; break;
      }
    }
    """


def _get_calendar_state(ws_url: str) -> dict:
    """
    获取日历面板当前状态：左月年份、左月月份、所有日期格子（idx, day, disabled）。
    Beast RPR 日历弹窗：含 RPR_outerPickerWrapper 的 PP_outerWrapper。
    """
    js = """
    (function(){
      """ + _get_rpr_panel_selector() + """
      if(!pp) return null;

      // 年份：input value 含「年」
      var yearInputs = pp.querySelectorAll('input');
      var years = [];
      for(var i=0;i<yearInputs.length;i++){
        var v = yearInputs[i].value;
        if(v && v.indexOf('年') > -1) years.push(parseInt(v));
      }

      // 月份：RPR_dateText
      var monthSpans = pp.querySelectorAll('[class*="RPR_dateText"]');
      var months = [];
      for(var i=0;i<monthSpans.length;i++){
        var t = monthSpans[i].textContent.trim();
        var idx = t.indexOf('月');
        if(idx > 0) months.push(parseInt(t.slice(0, idx)));
      }

      // 日期格子
      var tds = pp.querySelectorAll('td[role="date-cell"]');
      var cells = [];
      for(var i=0;i<tds.length;i++){
        cells.push({
          idx: i,
          day: parseInt(tds[i].textContent.trim()) || 0,
          outOfMonth: tds[i].classList.contains('RPR_outOfMonth_5-120-1'),
          disabled: tds[i].classList.contains('RPR_disabled_5-120-1')
        });
      }

      return {years: years, months: months, cellCount: cells.length, cells: cells};
    })()
    """
    return cdp_eval(ws_url, js)


def _click_calendar_arrow(ws_url: str, direction: str, panel: str, print_fn=print) -> bool:
    """
    点击日历面板箭头翻月。
    direction: 'prev'(-1月) 或 'next'(+1月)
    panel: 'left'(左月面板) 或 'right'(右月面板)
    索引映射（经实测）:
      icon-right[0] = 左月 +1
      icon-right[1] = 右月 +1
      icon-left[0]  = 左月 -1
      icon-left[1]  = 右月 -1
    """
    if direction == 'next':
        testid = 'beast-core-icon-right'
        idx = 0 if panel == 'left' else 1
    else:
        testid = 'beast-core-icon-left'
        idx = 0 if panel == 'left' else 1

    js = f"""
    (function(){{
      var panels = document.querySelectorAll('[class*="PP_outerWrapper"]');
      var pp = null;
      for(var _i=0;_i<panels.length;_i++){{
        if(panels[_i].querySelector('[class*="RPR_outerPickerWrapper"]')){{pp=panels[_i];break;}}
      }}
      if(!pp) return 'no-panel';
      var arrows = pp.querySelectorAll('[data-testid="{testid}"]');
      var a = arrows[{idx}];
      if(!a) return 'no-arrow:{testid}[{idx}]';
      var w = a.closest('[class*="ICN_outerWrapper"]') || a.parentElement;
      ['mouseenter','mousedown','mouseup','click'].forEach(function(ev){{
        w.dispatchEvent(new MouseEvent(ev, {{bubbles:true, cancelable:true}}));
      }});
      return 'ok';
    }})()
    """
    r = cdp_eval(ws_url, js)
    return r is not None and str(r) in ('ok', 'clicked')


def _navigate_panel_to_month(ws_url: str, panel: str,
                               current_year: int, current_month: int,
                               target_year: int, target_month: int,
                               print_fn=print) -> bool:
    """
    将左月或右月面板翻到目标年月。
    panel: 'left' 或 'right'
    """
    diff = (target_year - current_year) * 12 + (target_month - current_month)
    if diff == 0:
        return True

    direction = 'next' if diff > 0 else 'prev'
    label = '→' if diff > 0 else '←'
    print_fn(f"    翻{panel}月: {label} {abs(diff)} 次")

    for _ in range(abs(diff)):
        ok = _click_calendar_arrow(ws_url, direction, panel, print_fn)
        if not ok:
            print_fn(f"    箭头点击失败")
            return False
        time.sleep(0.35)

    time.sleep(0.2)
    return True


def _click_day_in_calendar(ws_url: str, year: int, month: int, day: int,
                             print_fn=print) -> bool:
    """
    在当前日历面板中点击指定日期。
    先获取面板状态，确认目标日期在左月还是右月，计算 td idx 后点击。
    """
    state = _get_calendar_state(ws_url)
    if not state:
        print_fn(f"    无法获取日历状态")
        return False

    years = state.get('years', [])
    months = state.get('months', [])
    cells = state.get('cells', [])

    if len(years) < 1 or len(months) < 1:
        print_fn(f"    日历月份读取失败: years={years} months={months}")
        return False

    left_year = years[0] if years else 0
    left_month = months[0] if months else 0
    right_year = years[1] if len(years) > 1 else left_year
    right_month = months[1] if len(months) > 1 else (left_month % 12 + 1)

    print_fn(f"    当前视图: {left_year}年{left_month}月 | {right_year}年{right_month}月，目标: {year}年{month}月{day}日")

    # 判断目标在左月还是右月
    if year == left_year and month == left_month:
        panel_idx = 0  # 左月，格子 0-41
    elif year == right_year and month == right_month:
        panel_idx = 1  # 右月，格子 42-83
    else:
        print_fn(f"    目标月份不在当前视图，需要翻月")
        return False

    # 在对应面板中找到目标 day
    panel_cells = cells[panel_idx * 42: (panel_idx + 1) * 42]
    target_cell_idx = None
    for cell in panel_cells:
        if cell['day'] == day and not cell['outOfMonth'] and not cell['disabled']:
            target_cell_idx = cell['idx']
            break

    if target_cell_idx is None:
        print_fn(f"    找不到 {day} 日的格子（可能是 outOfMonth 或 disabled）")
        return False

    # 点击该 td
    js_click = f"""
    (function(){{
      var panels = document.querySelectorAll('[class*="PP_outerWrapper"]');
      var pp = null;
      for(var _i=0;_i<panels.length;_i++){{
        if(panels[_i].querySelector('[class*="RPR_outerPickerWrapper"]')){{pp=panels[_i];break;}}
      }}
      if(!pp) return 'no-panel';
      var tds = pp.querySelectorAll('td[role="date-cell"]');
      var td = tds[{target_cell_idx}];
      if(!td) return 'td-not-found';
      var evts = ['mouseenter','mousedown','mouseup','click'];
      for(var _j=0;_j<evts.length;_j++){{
        td.dispatchEvent(new MouseEvent(evts[_j], {{bubbles:true, cancelable:true}}));
      }}
      return 'clicked:' + td.textContent.trim() + ' idx={target_cell_idx}';
    }})()
    """
    r = cdp_eval(ws_url, js_click)
    print_fn(f"    点击日期: {r}")
    return str(r).startswith('clicked:')


def set_custom_date_range(ws_url: str, start_date: str, end_date: str, print_fn=print) -> bool:
    """
    设置自定义日期范围，通过点击 Beast RPR 日历格子实现。
    流程：
    1. 打开下拉，选「自定义」
    2. 点击 RPR 输入框，触发日历弹窗
    3. 读取当前视图月份，判断是否需要翻月
    4. 点击开始日期格子
    5. 点击结束日期格子
    6. 点击「确认」按钮
    """
    print_fn(f"  自定义日期: {start_date} ~ {end_date}")

    # 解析日期
    try:
        from datetime import datetime
        s = datetime.strptime(start_date, '%Y-%m-%d')
        e = datetime.strptime(end_date, '%Y-%m-%d')
    except Exception as ex:
        print_fn(f"  日期格式错误: {ex}")
        return False

    # 校验：结束日期不能早于开始日期
    if e < s:
        print_fn(f"  错误：结束日期不能早于开始日期")
        return False

    # 校验：时间区间不能超过31天（页面限制）
    if (e - s).days > 31:
        print_fn(f"  错误：时间区间不能超过31天（当前 {(e-s).days} 天）")
        return False
        return False

    # Step1: 打开下拉，选「自定义」
    if not _open_time_range_dropdown(ws_url, print_fn):
        return False
    time.sleep(0.5)
    if not _click_option(ws_url, "自定义", print_fn):
        return False
    time.sleep(0.8)

    # Step2: 点击 RPR 输入框，弹出日历
    cdp_eval(ws_url, "document.querySelector('input.RPR_input_5-120-1').click()")
    time.sleep(1.2)

    # Step3: 获取当前日历视图，判断是否需要翻月
    state = _get_calendar_state(ws_url)
    if not state:
        print_fn("  日历面板未出现")
        return False

    years = state.get('years', [])
    months = state.get('months', [])
    if not years or not months:
        print_fn(f"  无法读取日历月份: {state}")
        return False

    left_year = years[0]
    left_month = months[0]
    right_year = years[1] if len(years) > 1 else left_year
    right_month = months[1] if len(months) > 1 else left_month
    print_fn(f"  日历当前: {left_year}年{left_month}月 | {right_year}年{right_month}月")

    # Step3a: 左月面板翻到 start_date 所在月
    if not (s.year == left_year and s.month == left_month):
        _navigate_panel_to_month(ws_url, 'left', left_year, left_month, s.year, s.month, print_fn)
        time.sleep(0.5)

    # Step3b: 右月面板独立翻到 end_date 所在月
    state2 = _get_calendar_state(ws_url)
    if state2 and len(state2.get('years', [])) > 1:
        right_year = state2['years'][1]
        right_month = state2['months'][1]
    if not (e.year == right_year and e.month == right_month):
        _navigate_panel_to_month(ws_url, 'right', right_year, right_month, e.year, e.month, print_fn)
        time.sleep(0.5)

    # Step4: 点击开始日期
    print_fn(f"  点击开始日期: {s.year}年{s.month}月{s.day}日")
    ok_start = _click_day_in_calendar(ws_url, s.year, s.month, s.day, print_fn)
    if not ok_start:
        print_fn("  开始日期点击失败")
        return False
    time.sleep(0.4)

    # Step5: 点击结束日期
    print_fn(f"  点击结束日期: {e.year}年{e.month}月{e.day}日")

    ok_end = _click_day_in_calendar(ws_url, e.year, e.month, e.day, print_fn)
    if not ok_end:
        print_fn("  结束日期点击失败")
        return False
    time.sleep(0.4)

    # Step6: 点击确认
    return _click_confirm_button(ws_url, print_fn)


def _click_confirm_button(ws_url: str, print_fn=print) -> bool:
    """点击 Beast RPR 日历弹窗的「确认」按钮"""
    js = """
    (function() {
      var panels = document.querySelectorAll('[class*="PP_outerWrapper"]');
      var pp = null;
      for(var _i=0;_i<panels.length;_i++){
        if(panels[_i].querySelector('[class*="RPR_outerPickerWrapper"]')){ pp=panels[_i]; break; }
      }
      var target = pp || document;
      var btns = target.querySelectorAll('button');
      for(var i=0;i<btns.length;i++){
        var t=btns[i].textContent.trim();
        if(t==='确认'||t==='确定'||t==='OK'){
          btns[i].click();
          return 'confirmed:'+t;
        }
      }
      return 'no-confirm-btn';
    })()
    """
    r = cdp_eval(ws_url, js)
    print_fn(f"  确认按钮: {r}")
    return str(r).startswith('confirmed')


def click_query_button(ws_url: str):
    """点击「查询」按钮"""
    js = """
    (function(){
      var btns = document.querySelectorAll('button');
      for (var i=0; i<btns.length; i++){
        if (btns[i].textContent.trim() === '查询') { btns[i].click(); return true; }
      }
      return false;
    })()
    """
    return cdp_eval(ws_url, js)


# ── 主流程 ────────────────────────────────────────────────────────────────────

def run(mode: str = "current", time_range: str = "", start_date: str = "", end_date: str = "",
        output_path: str = None, login_wait: int = 40, print_fn=print):
    """
    参数:
      time_range  : 预设时间区间，可选: '昨日' / '近7日' / '近30日' / '自定义'
                    也接受别名: '昨天'/'近7天'/'近30天'
                    留空则使用页面当前默认值（不修改）
      start_date  : 自定义开始日期 'YYYY-MM-DD'，time_range='自定义' 时生效
      end_date    : 自定义结束日期 'YYYY-MM-DD'，time_range='自定义' 时生效
    """
    install_temu_adapters()

    if output_path is None:
        output_path = desktop_path(timestamped_name("temu_goods_data"))

    ws_url = get_tab_ws_url(DOMAIN)
    if not ws_url:
        if mode == "new":
            print_fn(f"🌐 未找到 {DOMAIN} 的 tab，正在新开标签页...")
            ws_url = cdp_open_new_tab(GOODS_URL, wait=4.0)
            if not ws_url:
                print_fn(f"❌ 新开标签页失败，请检查 Chrome 是否已启动（CDP 端口 {CDP_PORT}）")
                return None
            print_fn("✅ 已打开商品数据页面，等待加载...")
            time.sleep(2)
        else:
            print_fn(f"❌ 未找到 {DOMAIN} 的 tab，请先在 Chrome 中打开 Temu 运营后台，或切换「全新页面」模式")
            return None

    print_fn(f"🔍 导航到商品数据页面...")
    cdp_navigate(ws_url, GOODS_URL)
    time.sleep(3)

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

    # ── 设置时间筛选 ──
    if time_range:
        real_range = TIME_RANGE_ALIASES.get(time_range, time_range)
        print_fn(f"📅 设置时间区间：{real_range}")

        if real_range == "自定义":
            if not start_date or not end_date:
                print_fn("  ⚠️ 自定义模式需要提供 start_date 和 end_date（格式 YYYY-MM-DD）")
            else:
                ok = set_custom_date_range(ws_url, start_date, end_date, print_fn)
                if ok:
                    print_fn(f"  ✓ 自定义日期设置成功: {start_date} ~ {end_date}")
                    time.sleep(0.5)
                    click_query_button(ws_url)
                    time.sleep(2.5)
                else:
                    print_fn("  ⚠️ 自定义日期设置失败，将使用页面当前日期")
        else:
            ok = set_preset_time_filter(ws_url, real_range, print_fn)
            if ok:
                print_fn(f"  ✓ 时间区间已设置为：{real_range}")
                time.sleep(0.5)
                click_query_button(ws_url)
                time.sleep(2.5)
            else:
                print_fn(f"  ⚠️ 「{real_range}」设置失败，将使用页面当前默认值")
    else:
        # 不修改时间，直接点查询
        click_query_button(ws_url)
        time.sleep(2)

    # ── 抓取所有页 ──
    print_fn("🚀 开始抓取商品数据...")
    headers = ["商品名称", "商品分类", "SPU", "SKC", "国家/地区", "支付件数", "销售趋势"]
    all_rows = []
    seen_keys = set()
    page = 1

    while True:
        print_fn(f"  正在抓取第 {page} 页...")
        rows = scrape_page(ws_url, print_fn)

        new_rows = []
        for row in rows:
            spu = row[2] if len(row) > 2 else ''
            skc = row[3] if len(row) > 3 else ''
            key = f"{spu}|{skc}"
            if key not in seen_keys:
                seen_keys.add(key)
                new_rows.append(row)

        all_rows.extend(new_rows)
        skipped = len(rows) - len(new_rows)
        if skipped > 0:
            print_fn(f"  ✓ 第 {page} 页获取 {len(rows)} 条（去重跳过 {skipped} 条）")
        else:
            print_fn(f"  ✓ 第 {page} 页获取 {len(rows)} 条")

        if len(rows) == 0:
            print_fn("  ⚠️ 本页无数据，停止")
            break

        if not has_next_page(ws_url):
            print_fn("  ↳ 已是最后一页")
            break

        cur_sig = get_page_signature(ws_url)
        clicked = click_next_page(ws_url)
        if not clicked:
            print_fn("  ↳ 无法点击下一页，停止")
            break

        changed = wait_page_change(ws_url, cur_sig)
        if not changed:
            print_fn("  ⚠️ 翻页后内容未变化，停止")
            break

        page += 1
        time.sleep(0.3)

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
                        help="时间区间: 昨日/近7日/近30日/自定义（留空使用页面默认值）")
    parser.add_argument("--start-date", default="", help="自定义开始日期 YYYY-MM-DD")
    parser.add_argument("--end-date", default="", help="自定义结束日期 YYYY-MM-DD")
    parser.add_argument("--output", default=None)
    parser.add_argument("--wait", type=int, default=40)
    args = parser.parse_args()
    run(mode=args.mode, time_range=args.time_range,
        start_date=args.start_date, end_date=args.end_date,
        output_path=args.output, login_wait=args.wait)
