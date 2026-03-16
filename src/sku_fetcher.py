"""
SKU 列表 + 价格抓取模块（bb-browser 实现）

通过 bb-browser 在用户真实 Chrome 里执行 adapter，逐页抓取店铺商品列表。
依赖：bb-browser daemon 运行中，Chrome 已登录 JD，mall.jd.com tab 已打开。
"""
import json
import logging
import re
import subprocess
import time
from typing import List, Dict

from .config import load_config

logger = logging.getLogger(__name__)


def _bb(args: list, cdp_port: str, timeout: int = 15):
    return subprocess.run(
        ["bb-browser"] + args + ["--port", cdp_port],
        capture_output=True, text=True, timeout=timeout,
    )


def _get_jd_tab(cdp_port: str) -> str:
    r = _bb(["tab", "list"], cdp_port)
    for line in r.stdout.splitlines():
        if "mall.jd.com" in line:
            m = re.search(r'\[(\d+)\]', line)
            if m:
                return m.group(1)
    return "0"


def _navigate_and_wait(url: str, cdp_port: str) -> bool:
    tab = _get_jd_tab(cdp_port)
    _bb(["tab", tab], cdp_port)
    _bb(["eval", f"location.href='{url}'", "--tab", tab], cdp_port)
    for _ in range(25):
        time.sleep(1)
        r = _bb(
            ["eval", "document.querySelectorAll('li.jSubObject').length", "--tab", tab],
            cdp_port, timeout=5,
        )
        try:
            if int(r.stdout.strip()) > 0:
                time.sleep(5)
                return True
        except Exception:
            pass
    time.sleep(5)
    return False


def _scrape_current_page(cdp_port: str) -> dict:
    r = _bb(["site", "jd/shop-prices", "--json"], cdp_port, timeout=60)
    if r.returncode != 0:
        return {"error": r.stderr.strip(), "items": []}
    try:
        out = r.stdout.strip()
        s = out.find("{")
        if s > 0:
            out = out[s:]
        parsed = json.loads(out)
        if not parsed.get("success", True):
            return {"error": parsed.get("error", "unknown"), "items": []}
        return parsed.get("data", parsed)
    except Exception as e:
        return {"error": str(e), "items": []}


def fetch_sku_list() -> List[Dict]:
    """
    逐页抓取店铺所有 SKU，返回列表，每项：
      {
        "sku_id":         "100012043978",
        "name":           "ASICS亚瑟士跑步鞋...",
        "original_price": 999.0,   # 划线价，可能为 None
        "current_price":  599.0,   # 前台价，可能为 None
        "product_url":    "https://item.jd.com/100012043978.html"
      }
    """
    cfg = load_config()
    shop_id   = cfg["shop"].get("shop_id", "")
    vendor_id = cfg["shop"].get("vendor_id", shop_id)
    cdp_port  = str(cfg.get("cdp_port", 9222))
    page_size = 60

    base_url = (
        f"https://mall.jd.com/advance_search-{vendor_id}-{shop_id}"
        f"-{shop_id}-0-0-0-1-{{page}}-{page_size}.html"
    )

    all_items: Dict[str, Dict] = {}
    page_no = 1
    consecutive_empty = 0

    logger.info(f"开始抓取店铺 SKU 列表（shop_id={shop_id}）...")
    ok = _navigate_and_wait(base_url.format(page=1), cdp_port)
    logger.info(f"第 1 页{'已加载' if ok else '超时，继续'}")

    while True:
        data  = _scrape_current_page(cdp_port)
        items = data.get("items", [])

        if not items:
            consecutive_empty += 1
            logger.warning(f"第 {page_no} 页无商品（连续 {consecutive_empty} 次）")
            if consecutive_empty >= 2:
                break
        else:
            consecutive_empty = 0
            for item in items:
                sku_id = item.get("skuId", "")
                if not sku_id or sku_id in all_items:
                    continue
                try:
                    orig = float(item["originalPrice"]) if item.get("originalPrice") else None
                except (TypeError, ValueError):
                    orig = None
                try:
                    cur = float(item["price"]) if item.get("price") else None
                except (TypeError, ValueError):
                    cur = None
                all_items[sku_id] = {
                    "sku_id":         sku_id,
                    "name":           item.get("name", ""),
                    "original_price": orig,
                    "current_price":  cur,
                    "product_url":    item.get("href", f"https://item.jd.com/{sku_id}.html"),
                }
            logger.info(
                f"第 {page_no} 页：{len(items)} 个，有价格 {data.get('withPrice', 0)}，累计 {len(all_items)}"
            )

        next_url = data.get("nextUrl")
        if not next_url:
            logger.info("已到最后一页")
            break

        page_no += 1
        ok = _navigate_and_wait(next_url, cdp_port)
        logger.info(f"第 {page_no} 页{'已加载' if ok else '超时，继续'}")

    result = list(all_items.values())
    logger.info(f"共抓取 {len(result)} 个 SKU")
    return result
