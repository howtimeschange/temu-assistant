"""
价格抓取模块（bb-browser 实现）

bb-browser adapter 在抓取 SKU 列表时已同步拿到前台价格，
此模块作为兼容层：直接透传 sku_list，保持 main.py 调用接口不变。
"""
from typing import List, Dict


async def fetch_prices(sku_list: List[Dict]) -> List[Dict]:
    """
    透传 sku_list（价格已由 fetch_sku_list 通过 bb-browser 抓取）。
    保持 main.py 的调用接口 `await fetch_prices(sku_list)` 不变。
    """
    return sku_list
