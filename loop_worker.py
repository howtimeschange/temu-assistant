#!/usr/bin/env python3
"""
循环巡检后台 worker。
由 cli.py 以子进程方式启动，支持 --export-excel 参数。
"""
import argparse
import os
import sys
import logging
import time

sys.path.insert(0, os.path.dirname(__file__))

from pathlib import Path
from src.config import reload_config
from src.sku_fetcher import fetch_sku_list
from src.checker import check_violations
from src.dingtalk import send_alert
from src.storage import save_results, cleanup_old_files
from src.excel_writer import write_price_excel

PROJ_DIR = Path(__file__).parent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("loop_worker")


def do_export(sku_list, cfg):
    excel_to_desktop = cfg["output"].get("excel_to_desktop", True)
    out_dir = Path.home() / "Desktop" if excel_to_desktop else PROJ_DIR / cfg["output"].get("data_dir", "data")
    out_file = write_price_excel(sku_list, out_dir)
    logger.info(f"✅ Excel 已导出：{out_file}")
    return out_file


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--export-excel", action="store_true", help="每轮巡检后导出 Excel 到桌面")
    args = parser.parse_args()
    export_excel = args.export_excel

    cfg = reload_config()
    interval = cfg["monitor"]["interval_minutes"] * 60
    logger.info(f"循环 worker 启动，每 {cfg['monitor']['interval_minutes']} 分钟执行一次")
    if export_excel:
        logger.info("每次巡检后将自动导出 Excel 到桌面")

    while True:
        start = time.time()
        logger.info("=" * 60)
        logger.info(f"开始巡检 | {cfg['shop']['shop_name']}")
        logger.info("=" * 60)

        try:
            sku_list = fetch_sku_list()
        except Exception as e:
            logger.error(f"SKU 抓取失败: {e}", exc_info=True)
            time.sleep(interval)
            continue

        if not sku_list:
            logger.warning("未抓取到任何 SKU，请检查 bb-browser daemon / Chrome 登录状态")
        else:
            success_count = sum(1 for r in sku_list if r.get("current_price") is not None)
            logger.info(f"共获取 {len(sku_list)} 个 SKU，有价格 {success_count} 个")
            violated = check_violations(sku_list)
            elapsed = time.time() - start
            if violated:
                logger.warning(f"发现 {len(violated)} 个破价 SKU！")
                for v in violated:
                    logger.warning(
                        f"  [{v['sku_id']}] {v['name'][:30]} "
                        f"吊牌价¥{v.get('original_price','N/A')} → "
                        f"前台价¥{v.get('current_price','N/A')} "
                        f"({v['ratio']*100:.1f}%)"
                    )
                send_alert(violated)
            else:
                logger.info("未发现破价 SKU ✅")
            save_results(sku_list, violated)
            cleanup_old_files()
            logger.info(f"巡检完成，耗时 {elapsed:.1f} 秒")

            if export_excel:
                try:
                    do_export(sku_list, cfg)
                except Exception as e:
                    logger.error(f"Excel 导出失败: {e}")

        cfg = reload_config()
        logger.info(f"等待 {cfg['monitor']['interval_minutes']} 分钟后下次执行...")
        time.sleep(interval)


if __name__ == "__main__":
    main()
