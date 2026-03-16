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

_BB_BIN: str = None


def _find_bb_browser() -> str:
    """
    查找 bb-browser 可执行文件的完整路径。
    优先级：PATH > nvm 目录 > npm root -g
    """
    global _BB_BIN
    if _BB_BIN:
        return _BB_BIN

    import shutil, glob, os

    # 1. 直接在 PATH 里找
    found = shutil.which("bb-browser")
    if found:
        _BB_BIN = found
        return _BB_BIN

    # 2. nvm 目录遍历
    nvm_dir = os.path.expanduser("~/.nvm/versions/node")
    if os.path.isdir(nvm_dir):
        candidates = sorted(glob.glob(f"{nvm_dir}/*/bin/bb-browser"), reverse=True)
        if candidates:
            _BB_BIN = candidates[0]
            logger.info(f"bb-browser 找到（nvm）：{_BB_BIN}")
            return _BB_BIN

    # 3. npm root -g
    try:
        r = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True, timeout=5)
        npm_root = r.stdout.strip()
        candidate = os.path.join(npm_root, ".bin", "bb-browser")
        if os.path.isfile(candidate):
            _BB_BIN = candidate
            logger.info(f"bb-browser 找到（npm root）：{_BB_BIN}")
            return _BB_BIN
    except Exception:
        pass

    raise FileNotFoundError(
        "找不到 bb-browser 命令。\n"
        "请确保已安装：npm install -g bb-browser\n"
        "并且 nvm 已初始化（source ~/.nvm/nvm.sh）"
    )


def _bb(args: list, cdp_port: str, timeout: int = 15):
    bb = _find_bb_browser()
    return subprocess.run(
        [bb] + args + ["--port", cdp_port],
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


def _scrape_item_price(url: str, cdp_port: str) -> dict:
    """访问单个商品详情页，用 item-price adapter 抓前台价"""
    tab = _get_jd_tab(cdp_port)
    _bb(["tab", tab], cdp_port)
    _bb(["eval", f"location.href='{url}'", "--tab", tab], cdp_port)
    # 等待 item.jd.com 页面加载（最多 20 秒）
    for _ in range(20):
        time.sleep(1)
        r = _bb(
            ["eval", "document.querySelector('.p-price') ? 1 : 0", "--tab", tab],
            cdp_port, timeout=5,
        )
        try:
            if int(r.stdout.strip()) == 1:
                time.sleep(1)
                break
        except Exception:
            pass

    r = _bb(["site", "jd/item-price", "--json"], cdp_port, timeout=30)
    if r.returncode != 0:
        return {}
    try:
        out = r.stdout.strip()
        s = out.find("{")
        if s > 0:
            out = out[s:]
        parsed = json.loads(out)
        return parsed.get("data", parsed)
    except Exception:
        return {}


def fill_missing_prices(sku_list: List[Dict], cdp_port: str = None) -> List[Dict]:
    """
    兜底逻辑：对列表中 current_price 为 None 的 SKU，逐个访问详情页补价格。
    直接修改 sku_list 中对应项，并在 price_source 字段标记来源为 'detail_page'。
    返回实际补全的 SKU 列表。
    """
    cfg = load_config()
    if cdp_port is None:
        cdp_port = str(cfg.get("cdp_port", 9222))

    missing = [item for item in sku_list if item.get("current_price") is None]
    if not missing:
        return []

    logger.info(f"【兜底】{len(missing)} 个 SKU 缺价格，开始访问详情页补全...")
    filled = []

    for idx, item in enumerate(missing, 1):
        url = item.get("product_url") or f"https://item.jd.com/{item['sku_id']}.html"
        logger.info(f"  [{idx}/{len(missing)}] 访问详情页：{url}")
        try:
            detail = _scrape_item_price(url, cdp_port)
            cur = detail.get("price")
            orig = detail.get("originalPrice")
            if cur:
                try:
                    cur = float(cur)
                except (TypeError, ValueError):
                    cur = None
            if orig:
                try:
                    orig = float(orig)
                except (TypeError, ValueError):
                    orig = None

            if cur is not None:
                item["current_price"] = cur
                item["price_source"] = "detail_page"
                # 如果原价也缺，一并补上
                if item.get("original_price") is None and orig is not None:
                    item["original_price"] = orig
                # 如果名称缺失，用详情页的补
                if not item.get("name") and detail.get("name"):
                    item["name"] = detail["name"]
                filled.append(item)
                logger.info(
                    f"    ✅ 补全：¥{cur}"
                    + (f"（原价 ¥{orig}）" if orig else "")
                )
            else:
                logger.warning(f"    ⚠️  详情页也未获取到价格，跳过")
        except Exception as e:
            logger.error(f"    ❌ 访问详情页失败：{e}")

        # 礼貌延迟，避免频繁请求
        time.sleep(1.5)

    logger.info(f"【兜底】完成，共补全 {len(filled)}/{len(missing)} 个 SKU")
    return filled


def fetch_sku_list() -> List[Dict]:
    """
    逐页抓取店铺所有 SKU，返回列表，每项：
      {
        "sku_id":         "100012043978",
        "name":           "ASICS亚瑟士跑步鞋...",
        "original_price": 999.0,   # 划线价，可能为 None
        "current_price":  599.0,   # 前台价，可能为 None
        "product_url":    "https://item.jd.com/100012043978.html",
        "price_source":   "list_page" | "detail_page"  # 来源标记
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
                    "price_source":   "list_page",
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

    # 兜底：补全仍然缺失价格的 SKU
    missing_count = sum(1 for r in result if r.get("current_price") is None)
    if missing_count > 0:
        logger.info(f"列表页仍有 {missing_count} 个 SKU 无价格，启动详情页兜底...")
        fill_missing_prices(result, cdp_port)
        still_missing = sum(1 for r in result if r.get("current_price") is None)
        logger.info(f"兜底后：{len(result) - still_missing} 个有价格，{still_missing} 个仍缺失")

    return result
