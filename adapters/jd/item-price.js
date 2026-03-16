/* @meta
{
  "name": "jd/item-price",
  "description": "读取当前京东商品详情页的前台价和划线价",
  "domain": "item.jd.com",
  "args": {},
  "readOnly": true,
  "example": "bb-browser site jd/item-price"
}
*/

async function(args) {
  // 等待价格元素渲染（最多 8 秒）
  for (let i = 0; i < 16; i++) {
    const priceEl = document.querySelector('.p-price .price') ||
                    document.querySelector('[class*="price"] .price') ||
                    document.querySelector('.price-box .price') ||
                    document.querySelector('#detail-price') ||
                    document.querySelector('span[class*="priceShow"]');
    if (priceEl && priceEl.innerText.trim()) break;
    await new Promise(r => setTimeout(r, 500));
  }

  // 滚动一下触发懒加载
  window.scrollTo(0, 300);
  await new Promise(r => setTimeout(r, 400));
  window.scrollTo(0, 0);
  await new Promise(r => setTimeout(r, 300));

  // 当前价（前台价）—— 多选择器兼容不同页面结构
  const priceSelectors = [
    '.p-price .price',
    '.p-price span.price',
    '[class*="price"] .price',
    '.price-box .price',
    '#detail-price',
    'span[class*="priceShow"]',
    '.J-p-' // SKU 价格容器
  ];
  let price = null;
  for (const sel of priceSelectors) {
    const el = document.querySelector(sel);
    if (el && el.innerText.trim()) {
      price = el.innerText.trim().replace(/[^0-9.]/g, '') || null;
      if (price) break;
    }
  }

  // 划线原价
  const delPriceSelectors = [
    '.p-price del',
    '.price-box del',
    '[class*="del"] .price',
    'del .price',
    '.p-price .del-price',
    'del[class*="price"]'
  ];
  let originalPrice = null;
  for (const sel of delPriceSelectors) {
    const el = document.querySelector(sel);
    if (el && el.innerText.trim()) {
      originalPrice = el.innerText.trim().replace(/[^0-9.]/g, '') || null;
      if (originalPrice) break;
    }
  }

  // 商品名
  const nameEl = document.querySelector('.sku-name') ||
                 document.querySelector('#itemName') ||
                 document.querySelector('h1[class*="name"]') ||
                 document.querySelector('.product-intro .sku-name');
  const name = nameEl ? nameEl.innerText.trim() : document.title.replace(' - 京东', '').trim();

  // 当前 SKU ID（从 URL 或 window 变量取）
  let skuId = '';
  const m = location.href.match(/\/(\d+)\.html/);
  if (m) skuId = m[1];
  if (!skuId && window.pageConfig && window.pageConfig.product) {
    skuId = String(window.pageConfig.product.skuId || '');
  }

  return {
    skuId,
    name,
    price,
    originalPrice,
    url: location.href
  };
}
