#!/usr/bin/env python3
"""
美股5分钟K线每日增量更新（约06:00北京时间触发）。

触发时间：北京周二~周六 06:00（对应美股周一~周五收盘次日凌晨）
  - 美股 16:00 ET 收盘 ≈ 北京次日 04:00/05:00（冬/夏令时）
  - 06:00 北京留有充足余量确保数据可用
  - 美股节假日：us_trade_calendar 中 is_open=0，pending 为空，任务自动 no-op

用法：
    python scripts/daily_update_us_minute.py           # 自动检测待更新交易日
    python scripts/daily_update_us_minute.py --date 20260521
"""
import sys
import argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from stockdb.utils.logger import log


def main():
    parser = argparse.ArgumentParser(description="美股5分钟K线每日增量更新")
    parser.add_argument("--date", help="强制指定美股交易日 YYYYMMDD")
    args = parser.parse_args()

    log.info(f"daily_update_us_minute 启动: {datetime.now():%Y-%m-%d %H:%M:%S}")

    try:
        from stockdb.utils.us_session import get_us_pending_trade_dates
        if args.date:
            trade_dates = [args.date]
        else:
            trade_dates = get_us_pending_trade_dates("us_minute_bar_5min", "20260101")
    except Exception as e:
        log.error(f"获取待更新交易日失败: {e}")
        return

    if not trade_dates:
        log.info("美股5分钟K线：没有待更新的交易日（可能为节假日或已是最新）")
        return

    log.info(f"待更新5分钟K线（美股）: {trade_dates}")

    from stockdb.loaders.us_minute_bar import load_us_minute_5min_daily
    for td in trade_dates:
        log.info(f"── 美股5分钟K线 {td}")
        try:
            n = load_us_minute_5min_daily(td)
            log.info(f"us_minute_bar_5min {td}: {n} rows")
        except Exception as e:
            log.error(f"us_minute_bar_5min {td} 失败: {e}")

    log.info(f"daily_update_us_minute 完成: {datetime.now():%Y-%m-%d %H:%M:%S}")


if __name__ == "__main__":
    main()
