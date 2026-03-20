/**
 * Temu 商品数据 adapter
 * 页面：https://agentseller.temu.com/newon/goods-data
 * Beast 组件库（非 antd）
 */

async function scrapeCurrentPage() {
  const rows = document.querySelectorAll('tbody tr.TB_tr_5-120-1');
  const results = [];

  for (const row of rows) {
    const tds = row.querySelectorAll('td.TB_td_5-120-1');
    if (tds.length < 3) continue;

    // td[1] = 商品信息（商品名、分类、SPU、SKC）
    const infoTd = tds[0]; // 跳过 checkbox td
    const nameLine = infoTd.querySelector('a, [class*="title"], [class*="name"]');
    const fullText = infoTd.innerText.trim();

    // 提取各字段
    const lines = fullText.split('\n').map(s => s.trim()).filter(Boolean);
    let goodsName = '', category = '', spu = '', skc = '';
    for (let i = 0; i < lines.length; i++) {
      if (lines[i] === 'SPU：') { spu = lines[i + 1] || ''; }
      else if (lines[i] === 'SKC：') { skc = lines[i + 1] || ''; }
      else if (!goodsName && !lines[i].match(/^(SPU|SKC)/) && i === 0) goodsName = lines[i];
      else if (goodsName && !category && !lines[i].match(/^(SPU|SKC)/)) category = lines[i];
    }

    // td[2] = 国家/地区
    const country = tds[1] ? tds[1].innerText.trim() : '';

    // td[3] = 支付件数 + 趋势（如 "59\n73.52%"）
    const payText = tds[2] ? tds[2].innerText.trim() : '';
    const payLines = payText.split('\n').map(s => s.trim()).filter(Boolean);
    const payCount = payLines[0] || '';
    const trend = payLines[1] || '';

    if (goodsName || spu) {
      results.push({ goodsName, category, spu, skc, country, payCount, trend });
    }
  }

  return results;
}

async function getTotalPages() {
  // 分页：PGT_totalText_5-120-1 显示 "共有 233 条"
  const totalEl = document.querySelector('.PGT_totalText_5-120-1');
  if (!totalEl) return 1;
  const match = totalEl.textContent.match(/(\d+)/);
  const total = match ? parseInt(match[1]) : 0;

  // 每页条数（默认 30）
  const sizeEl = document.querySelector('.PGT_sizeChanger_5-120-1 [class*="ST_selectValue"], .PGT_sizeChanger_5-120-1 input');
  let pageSize = 30;
  if (sizeEl) {
    const sizeMatch = sizeEl.textContent.match(/(\d+)/);
    if (sizeMatch) pageSize = parseInt(sizeMatch[1]);
  }

  return Math.ceil(total / pageSize);
}

async function hasNextPage() {
  const nextBtn = document.querySelector('.PGT_next_5-120-1');
  if (!nextBtn) return false;
  return !nextBtn.classList.contains('PGT_disabled_5-120-1');
}

async function clickNextPage() {
  const nextBtn = document.querySelector('.PGT_next_5-120-1');
  if (nextBtn && !nextBtn.classList.contains('PGT_disabled_5-120-1')) {
    nextBtn.click();
    return true;
  }
  return false;
}

// 设置时间筛选（下拉选择，选项如：近7天/近30天等）
async function setTimeFilter(optionText) {
  // 找时间区间 label 的 next sibling 里的 Select
  let timeSelect = null;
  const labels = document.querySelectorAll('*');
  for (const el of labels) {
    if (el.children.length === 0 && el.textContent.trim() === '时间区间') {
      const field = el.nextElementSibling;
      if (field) {
        timeSelect = field.querySelector('[data-testid="beast-core-select"]');
      }
      break;
    }
  }

  if (!timeSelect) return { ok: false, msg: 'time-select-not-found' };

  // 点击打开下拉
  timeSelect.click();
  await new Promise(r => setTimeout(r, 500));

  // 找选项
  const optionEls = document.querySelectorAll('[data-testid="beast-core-select-option"], [class*="ST_option"]');
  for (const opt of optionEls) {
    if (opt.textContent.trim().includes(optionText)) {
      opt.click();
      return { ok: true };
    }
  }

  // 关闭下拉
  document.body.click();
  return { ok: false, msg: 'option-not-found', available: Array.from(optionEls).map(o => o.textContent.trim()) };
}

// 点击「查询」按钮
async function clickQuery() {
  const btns = document.querySelectorAll('button');
  for (const btn of btns) {
    if (btn.textContent.trim() === '查询') {
      btn.click();
      return true;
    }
  }
  return false;
}

// 等待表格数据加载完成
async function waitForTableLoad(expectedChange) {
  const getRowCount = () => document.querySelectorAll('tbody tr.TB_tr_5-120-1').length;
  const start = getRowCount();
  const startTime = Date.now();

  while (Date.now() - startTime < 8000) {
    await new Promise(r => setTimeout(r, 400));
    const current = getRowCount();
    // 如果行数变化了（翻页/查询刷新），认为加载完成
    if (expectedChange && current !== start) return true;
    // 如果有加载态消失
    const loading = document.querySelector('[class*="loading"], [class*="Loading"], .TB_loading');
    if (!loading && current > 0) return true;
  }
  return getRowCount() > 0;
}
