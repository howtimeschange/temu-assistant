/* @meta
{
  "name": "temu/store-items",
  "description": "抓取 Temu 店铺商品列表（Items tab），忽略 Explore Temu picks 栏目，支持 See More",
  "domain": "www.temu.com",
  "args": {},
  "readOnly": false,
  "example": "bb-browser site temu/store-items"
}
*/

async function(args) {
  // 等待商品列表渲染（最多 15s）
  const itemSelectors = [
    '[class*="goods-item"]',
    '[class*="GoodsItem"]',
    '[class*="product-item"]',
    '[class*="ProductItem"]',
    '[class*="item-card"]',
    '[data-type="goods"]'
  ];

  let itemEls = [];
  for (let i = 0; i < 30; i++) {
    for (const sel of itemSelectors) {
      itemEls = document.querySelectorAll(sel);
      if (itemEls.length > 0) break;
    }
    if (itemEls.length > 0) break;
    await new Promise(r => setTimeout(r, 500));
  }

  // 点击 "See More" 按钮（如果存在）
  const seeMoreBtns = Array.from(document.querySelectorAll('button, [role="button"], a'))
    .filter(el => /see more/i.test(el.innerText) && el.offsetParent !== null);
  for (const btn of seeMoreBtns) {
    btn.click();
    await new Promise(r => setTimeout(r, 1500));
  }

  // 分段滚动触发懒加载
  const totalH = document.body.scrollHeight;
  for (let s = 1; s <= 8; s++) {
    window.scrollTo(0, (totalH / 8) * s);
    await new Promise(r => setTimeout(r, 300));
  }
  window.scrollTo(0, 0);
  await new Promise(r => setTimeout(r, 500));

  // 重新获取（滚动后可能有更多）
  for (const sel of itemSelectors) {
    const els = document.querySelectorAll(sel);
    if (els.length > itemEls.length) itemEls = els;
  }

  // 找出「Explore Temu's picks」模块的边界，排除该模块内的商品
  function isInExploreSection(el) {
    let node = el;
    while (node && node !== document.body) {
      const text = (node.getAttribute('class') || '') + ' ' + (node.innerText || '').slice(0, 100);
      if (/explore temu.{0,5}picks/i.test(text)) return true;
      // 检查前兄弟/父节点是否有该标题
      const prev = node.previousElementSibling;
      if (prev && /explore temu.{0,5}picks/i.test(prev.innerText || '')) return true;
      node = node.parentElement;
    }
    return false;
  }

  const items = [];

  itemEls.forEach(el => {
    // 跳过 Explore Temu's picks 区域
    if (isInExploreSection(el)) return;

    // 商品名
    const nameEl = el.querySelector('[class*="title"], [class*="name"], [class*="goods-name"]');
    const name = nameEl ? nameEl.innerText.trim() : '';

    // 价格
    const priceEl = el.querySelector('[class*="price"] [class*="value"], [class*="price"]:not([class*="original"]), [class*="sale-price"]');
    const price = priceEl ? priceEl.innerText.trim().replace(/[^\d.,]/g, '') : '';

    // 原价
    const origEl = el.querySelector('[class*="original-price"], [class*="origin-price"], del, s');
    const originalPrice = origEl ? origEl.innerText.trim().replace(/[^\d.,]/g, '') : '';

    // 评分
    const ratingEl = el.querySelector('[class*="rating"], [aria-label*="star"], [class*="score"]');
    const rating = ratingEl ? (ratingEl.getAttribute('aria-label') || ratingEl.innerText.trim()) : '';

    // 评价数
    const reviewCountEl = el.querySelector('[class*="review-count"], [class*="sold"], [class*="comment-count"]');
    const reviewCount = reviewCountEl ? reviewCountEl.innerText.trim() : '';

    // 链接
    const linkEl = el.querySelector('a[href*="/goods.html"], a[href*="goods_id"], a');
    const href = linkEl ? linkEl.href : '';

    // 图片
    const imgEl = el.querySelector('img');
    const imgSrc = imgEl ? imgEl.src : '';

    if (name || price) {
      items.push({ name, price, originalPrice, rating, reviewCount, href, imgSrc });
    }
  });

  // 翻页检测
  const nextBtn = document.querySelector(
    '.ant-pagination-next:not(.ant-pagination-disabled), ' +
    '[class*="pagination"] [aria-label="Next"]:not([disabled]), ' +
    '[class*="next-page"]:not([disabled])'
  );
  const hasNextPage = !!nextBtn;

  const pageEl = document.querySelector('.ant-pagination-item-active, [class*="page-item"][class*="active"]');
  const currentPage = pageEl ? parseInt(pageEl.innerText) || 1 : 1;

  return {
    items,
    hasNextPage,
    currentPage,
    url: location.href,
    title: document.title
  };
}
