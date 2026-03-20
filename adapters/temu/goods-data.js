/* @meta
{
  "name": "temu/goods-data",
  "description": "抓取 Temu 商家后台「数据中心-商品数据」表格所有行（含翻页检测）",
  "domain": "agentseller.temu.com",
  "args": {},
  "readOnly": true,
  "example": "bb-browser site temu/goods-data"
}
*/

async function(args) {
  // 等待表格渲染（最多 15s）
  for (let i = 0; i < 30; i++) {
    const rows = document.querySelectorAll('table tbody tr, [class*="table"] [class*="row"], [class*="Table"] [class*="Row"]');
    if (rows.length > 0) break;
    await new Promise(r => setTimeout(r, 500));
  }

  // 滚动到底部触发懒加载
  window.scrollTo(0, document.body.scrollHeight);
  await new Promise(r => setTimeout(r, 800));
  window.scrollTo(0, 0);
  await new Promise(r => setTimeout(r, 500));

  // 通用表格抓取：先找表头
  function getHeaders(table) {
    const ths = table.querySelectorAll('thead th, thead td');
    if (ths.length > 0) return Array.from(ths).map(th => th.innerText.trim());
    // 首行作为表头
    const firstRow = table.querySelector('tr');
    if (firstRow) return Array.from(firstRow.querySelectorAll('td, th')).map(c => c.innerText.trim());
    return [];
  }

  function getRows(table, skipFirst) {
    const rows = [];
    const trs = table.querySelectorAll(skipFirst ? 'tbody tr' : 'tr');
    trs.forEach((tr, idx) => {
      if (skipFirst && idx === 0) return;
      const cells = Array.from(tr.querySelectorAll('td, th')).map(c => c.innerText.trim());
      if (cells.some(c => c !== '')) rows.push(cells);
    });
    return rows;
  }

  // 找主表格
  let headers = [];
  let items = [];

  const tables = document.querySelectorAll('table');
  if (tables.length > 0) {
    // 取最大的 table（行数最多）
    let maxTable = null, maxRows = 0;
    tables.forEach(t => {
      const rc = t.querySelectorAll('tbody tr').length || t.querySelectorAll('tr').length;
      if (rc > maxRows) { maxRows = rc; maxTable = t; }
    });
    if (maxTable) {
      headers = getHeaders(maxTable);
      items = getRows(maxTable, maxTable.querySelector('thead') !== null);
    }
  }

  // 兜底：React 虚拟列表（class 含 table/row）
  if (items.length === 0) {
    const headEls = document.querySelectorAll('[class*="thead"] [class*="th"], [class*="header"] [class*="cell"]');
    if (headEls.length > 0) headers = Array.from(headEls).map(e => e.innerText.trim());

    const rowEls = document.querySelectorAll('[class*="tbody"] [class*="tr"], [class*="table-row"]');
    rowEls.forEach(row => {
      const cells = Array.from(row.querySelectorAll('[class*="td"], [class*="cell"]')).map(c => c.innerText.trim());
      if (cells.some(c => c !== '')) items.push(cells);
    });
  }

  // 翻页检测
  let hasNextPage = false;
  let currentPage = 1;
  let totalPages = 1;

  // 找分页按钮（Temu 后台常见 ant-design pagination）
  const nextBtn = document.querySelector(
    '.ant-pagination-next:not(.ant-pagination-disabled), ' +
    '[class*="pagination"] [aria-label="Next"], ' +
    '[class*="pagination"] button:last-child:not([disabled]), ' +
    '[class*="next-page"]:not([disabled])'
  );
  if (nextBtn) {
    const disabled = nextBtn.disabled || nextBtn.classList.contains('ant-pagination-disabled') ||
                     nextBtn.getAttribute('aria-disabled') === 'true';
    hasNextPage = !disabled;
  }

  // 读取当前页码
  const pageInput = document.querySelector('.ant-pagination-item-active, [class*="pagination-item-active"]');
  if (pageInput) currentPage = parseInt(pageInput.innerText) || 1;

  const totalEl = document.querySelector('[class*="pagination"] .ant-pagination-total-text, [class*="total"]');
  const totalText = totalEl ? totalEl.innerText : '';

  return {
    headers,
    items,
    hasNextPage,
    currentPage,
    totalPages,
    totalText,
    url: location.href
  };
}
