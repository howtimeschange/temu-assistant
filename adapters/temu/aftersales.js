/* @meta
{
  "name": "temu/aftersales",
  "description": "抓取 Temu 商家后台售后管理页面表格数据，含弹窗检测",
  "domain": "agentseller.temu.com",
  "args": {},
  "readOnly": false,
  "example": "bb-browser site temu/aftersales"
}
*/

async function(args) {
  // 先检测并关闭弹窗
  const popupSelectors = [
    '[class*="modal"] button[class*="close"]',
    '[class*="dialog"] button[class*="close"]',
    '[class*="popup"] button[class*="close"]',
    '.ant-modal-close',
    '[class*="modal"] .ant-btn-primary',
    '[class*="dialog"] button:last-child',
    '[aria-label="Close"]',
    '[aria-label="close"]'
  ];

  let popupClosed = false;
  for (const sel of popupSelectors) {
    const btn = document.querySelector(sel);
    if (btn && btn.offsetParent !== null) {
      btn.click();
      await new Promise(r => setTimeout(r, 600));
      popupClosed = true;
      break;
    }
  }

  // 等待表格
  for (let i = 0; i < 30; i++) {
    const rows = document.querySelectorAll('table tbody tr');
    if (rows.length > 0) break;
    await new Promise(r => setTimeout(r, 500));
  }

  await new Promise(r => setTimeout(r, 800));

  // 抓取表格
  let headers = [];
  let items = [];

  const table = (() => {
    const tables = document.querySelectorAll('table');
    let max = null, maxR = 0;
    tables.forEach(t => {
      const rc = t.querySelectorAll('tbody tr').length;
      if (rc > maxR) { maxR = rc; max = t; }
    });
    return max;
  })();

  if (table) {
    const ths = table.querySelectorAll('thead th, thead td');
    headers = Array.from(ths).map(th => th.innerText.trim());
    const trs = table.querySelectorAll('tbody tr');
    trs.forEach(tr => {
      const cells = Array.from(tr.querySelectorAll('td')).map(c => c.innerText.trim());
      if (cells.some(c => c !== '')) items.push(cells);
    });
  }

  // 翻页检测
  const nextBtn = document.querySelector(
    '.ant-pagination-next:not(.ant-pagination-disabled), ' +
    'li.ant-pagination-next:not(.ant-pagination-disabled)'
  );
  const hasNextPage = nextBtn
    ? !(nextBtn.classList.contains('ant-pagination-disabled') || nextBtn.querySelector('button[disabled]'))
    : false;

  const pageEl = document.querySelector('.ant-pagination-item-active');
  const currentPage = pageEl ? parseInt(pageEl.innerText) || 1 : 1;

  // 检测是否还有弹窗未关闭
  const modalVisible = !!document.querySelector('.ant-modal-wrap:not([style*="display: none"]), [class*="modal"][class*="visible"]');

  return {
    headers,
    items,
    hasNextPage,
    currentPage,
    popupClosed,
    modalStillVisible: modalVisible,
    url: location.href
  };
}
