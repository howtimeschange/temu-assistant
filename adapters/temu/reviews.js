/* @meta
{
  "name": "temu/reviews",
  "description": "抓取 Temu 店铺评价列表（评分/文字/时间/图片/商品名），含翻页检测",
  "domain": "www.temu.com",
  "args": {},
  "readOnly": true,
  "example": "bb-browser site temu/reviews"
}
*/

async function(args) {
  // 等待评价列表渲染（最多 15s）
  const reviewSelectors = [
    '[class*="review-item"]',
    '[class*="ReviewItem"]',
    '[class*="review_item"]',
    '[data-type="review"]',
    '[class*="comment-item"]',
    '[class*="feedback-item"]'
  ];

  let reviewEls = [];
  for (let i = 0; i < 30; i++) {
    for (const sel of reviewSelectors) {
      reviewEls = document.querySelectorAll(sel);
      if (reviewEls.length > 0) break;
    }
    if (reviewEls.length > 0) break;
    await new Promise(r => setTimeout(r, 500));
  }

  // 滚动加载
  const scrollStep = Math.floor(window.innerHeight * 0.8);
  for (let s = 0; s < 5; s++) {
    window.scrollBy(0, scrollStep);
    await new Promise(r => setTimeout(r, 400));
  }
  window.scrollTo(0, 0);
  await new Promise(r => setTimeout(r, 500));

  // 重新获取
  for (const sel of reviewSelectors) {
    const els = document.querySelectorAll(sel);
    if (els.length > reviewEls.length) reviewEls = els;
  }

  const reviews = [];

  reviewEls.forEach(el => {
    // 评分（星级）
    const ratingEl = el.querySelector('[class*="star"][class*="filled"], [class*="rating"], [aria-label*="star"], [class*="score"]');
    let rating = '';
    if (ratingEl) {
      rating = ratingEl.getAttribute('aria-label') || ratingEl.innerText.trim();
      // 计算实心星数
      const filledStars = el.querySelectorAll('[class*="star"][class*="filled"], [class*="star-on"], svg[class*="star"]');
      if (filledStars.length > 0) rating = filledStars.length.toString();
    }

    // 评价文字
    const textEl = el.querySelector('[class*="review-text"], [class*="comment-text"], [class*="content"], p');
    const text = textEl ? textEl.innerText.trim() : el.innerText.split('\n')[0].trim();

    // 时间
    const timeEl = el.querySelector('[class*="time"], [class*="date"], time');
    const time = timeEl ? (timeEl.getAttribute('datetime') || timeEl.innerText.trim()) : '';

    // 用户名
    const userEl = el.querySelector('[class*="username"], [class*="user-name"], [class*="nickname"], [class*="author"]');
    const username = userEl ? userEl.innerText.trim() : '';

    // 商品名
    const goodsEl = el.querySelector('[class*="goods-name"], [class*="product-name"], [class*="item-name"], [class*="sku"]');
    const goodsName = goodsEl ? goodsEl.innerText.trim() : '';

    // 图片
    const imgs = Array.from(el.querySelectorAll('img[src*="temu"], img[class*="review"], img[class*="image"]'))
      .map(img => img.src)
      .filter(src => src && !src.includes('avatar') && !src.includes('icon'));

    reviews.push({ rating, text, time, username, goodsName, images: imgs.join(',') });
  });

  // 翻页检测
  const nextBtn = document.querySelector(
    '[class*="pagination"] [aria-label="Next"]:not([disabled]), ' +
    '[class*="pagination"] button:last-child:not([disabled]), ' +
    '.ant-pagination-next:not(.ant-pagination-disabled), ' +
    '[class*="next-page"]:not([disabled])'
  );
  const hasNextPage = !!nextBtn;

  const pageEl = document.querySelector('.ant-pagination-item-active, [class*="active"][class*="page"]');
  const currentPage = pageEl ? parseInt(pageEl.innerText) || 1 : 1;

  return {
    reviews,
    hasNextPage,
    currentPage,
    url: location.href,
    title: document.title
  };
}
