#!/usr/bin/env python3
"""
每日5分钟K线 + 筹码分布增量更新（15:30 运行，收盘后30分钟）。

Part 1 — 5分钟K线：Baostock，数据收盘即可用，约 5 分钟
Part 2 — 筹码分布：AKShare stock_cyq_em，全量更新约 90 分钟

用法：
    python scripts/daily_update_minute.py               # 自动检测待更新交易日
    python scripts/daily_update_minute.py --date 20260320
    python scripts/daily_update_minute.py --skip-chip   # 仅更新5分钟K线
"""
import sys
import argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from stockdb.utils.logger import log
from stockdb.db import engine
from sqlalchemy import text


def get_pending_trade_dates() -> list:
    """获取 minute_bar_5min 尚未更新的交易日（最多30天，升序）"""
    sql = text("""
        SELECT to_char(tc.cal_date, 'YYYYMMDD')
        FROM trade_calendar tc
        WHERE tc.is_open = 1
          AND tc.cal_date >= '2024-01-01'
          AND tc.cal_date <= CURRENT_DATE
          AND NOT EXISTS (
              SELECT 1 FROM data_update_log dul
              WHERE dul.table_name = 'minute_bar_5min'
                AND dul.trade_date = tc.cal_date
                AND dul.status IN ('success', 'partial')
          )
        ORDER BY tc.cal_date DESC
        LIMIT 30
    """)
    with engine.connect() as conn:
        rows = conn.execute(sql).fetchall()
    return [r[0] for r in reversed(rows)]


def main():
    parser = argparse.ArgumentParser(description="每日5分钟K线 + 筹码分布增量更新")
    parser.add_argument("--date",      help="强制指定交易日 YYYYMMDD")
    parser.add_argument("--skip-chip", action="store_true",
                        help="跳过筹码分布更新（仅更新5分钟K线）")
    args = parser.parse_args()

    log.info(f"daily_update_minute 启动: {datetime.now():%Y-%m-%d %H:%M:%S}")

    # ── Part 1: 5分钟K线 ─────────────────────────────────────
    if args.date:
        trade_dates = [args.date]
    else:
        trade_dates = get_pending_trade_dates()

    if trade_dates:
        from stockdb.fetchers.baostock_fetcher import _ensure_login
        _ensure_login()

        from stockdb.loaders.minute_bar import load_minute_5min_daily
        log.info(f"待更新5分钟K线: {trade_dates}")
        for td in trade_dates:
            log.info(f"── 5分钟K线 {td}")
            try:
                n = load_minute_5min_daily(td)
                log.info(f"5分钟K线 {td}: {n} rows")
            except Exception as e:
                log.error(f"5分钟K线 {td} 失败: {e}")
    else:
        log.info("5分钟K线: 无待更新交易日")

    # ── Part 2: 筹码分布（全量，约90分钟）─────────────────────
    if not args.skip_chip:
        log.info("开始筹码分布全量更新（约90分钟）...")
        try:
            from stockdb.loaders.chip_distribution import load_chip_daily
            n = load_chip_daily()
            log.info(f"筹码分布完成: {n} rows")
        except Exception as e:
            log.error(f"筹码分布更新失败: {e}")

    log.info(f"daily_update_minute 完成: {datetime.now():%Y-%m-%d %H:%M:%S}")


if __name__ == "__main__":
    main()
