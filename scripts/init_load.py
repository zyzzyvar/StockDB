#!/usr/bin/env python3
"""
全量历史数据初始化加载脚本。

用法：
    python scripts/init_load.py [--start 19901219] [--end 20250101]
    python scripts/init_load.py --tables daily_price,adj_factor  # 只加载指定表

特点：
    - 断点续传：已成功加载的交易日自动跳过
    - 按日期批量处理，遇单日失败跳过继续
    - 预计总耗时 4~10 小时（受 Tushare 频率限制）
"""
import sys
import argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from stockdb.utils.logger import log
from stockdb.utils.date_utils import get_trade_dates, today_str
from stockdb.config import INIT_START_DATE

# ── 加载顺序（优先级高→低）────────────────────────────────
LOAD_ORDER = [
    "trade_calendar",
    "stock_basic",
    "index_basic",
    "index_daily",
    "daily_price",
    "adj_factor",
    "daily_fundamental",
    "money_flow",
    "margin_detail",
    "top_list",
    "block_trade",
    "limit_list",
]


def load_table(table: str, trade_dates: list, start_date: str, end_date: str):
    log.info(f"{'='*50}")
    log.info(f"开始加载: {table}")
    log.info(f"{'='*50}")

    if table == "trade_calendar":
        from stockdb.loaders.trade_calendar import load_trade_calendar
        load_trade_calendar(start_date, end_date)

    elif table == "stock_basic":
        from stockdb.loaders.stock_basic import load_stock_basic
        load_stock_basic()

    elif table == "index_basic":
        from stockdb.loaders.index_data import load_index_basic
        load_index_basic()

    elif table == "index_daily":
        from stockdb.loaders.index_data import load_index_daily
        load_index_daily(start_date, end_date)

    elif table == "daily_price":
        from stockdb.loaders.daily_price import load_daily_price_batch
        total = load_daily_price_batch(trade_dates, skip_existing=True)
        log.info(f"daily_price 合计 upserted: {total} rows")

    elif table == "adj_factor":
        # 按股票加载（逐只获取全量复权因子更高效）
        from stockdb.loaders.adj_factor import load_adj_factor_for_codes, get_all_ts_codes
        ts_codes = get_all_ts_codes()
        log.info(f"adj_factor: 共 {len(ts_codes)} 只股票")
        total = load_adj_factor_for_codes(ts_codes, start_date=start_date, end_date=end_date)
        log.info(f"adj_factor 合计 upserted: {total} rows")

    elif table == "daily_fundamental":
        from stockdb.loaders.daily_fundamental import load_daily_fundamental_batch
        total = load_daily_fundamental_batch(trade_dates, skip_existing=True)
        log.info(f"daily_fundamental 合计 upserted: {total} rows")

    elif table == "money_flow":
        # 资金流向数据通常从 2010 年起有数据
        mf_start = max(start_date, "20100101")
        mf_dates = [d for d in trade_dates if d >= mf_start]
        from stockdb.loaders.money_flow import load_money_flow_batch
        total = load_money_flow_batch(mf_dates, skip_existing=True)
        log.info(f"money_flow 合计 upserted: {total} rows")

    elif table == "margin_detail":
        # 融资融券从 2010 年 3 月启动
        mg_start = max(start_date, "20100331")
        mg_dates = [d for d in trade_dates if d >= mg_start]
        from stockdb.loaders.margin_detail import load_margin_detail_batch
        total = load_margin_detail_batch(mg_dates, skip_existing=True)
        log.info(f"margin_detail 合计 upserted: {total} rows")

    elif table == "top_list":
        from stockdb.loaders.top_list import load_top_list_batch
        total = load_top_list_batch(trade_dates, skip_existing=True)
        log.info(f"top_list 合计 upserted: {total} rows")

    elif table == "block_trade":
        from stockdb.loaders.block_trade import load_block_trade_batch
        total = load_block_trade_batch(trade_dates, skip_existing=True)
        log.info(f"block_trade 合计 upserted: {total} rows")

    elif table == "limit_list":
        # 按月分段拉取（接口限制1次/分钟）
        ll_start = max(start_date, "20160101")
        from stockdb.loaders.limit_list import load_limit_list
        total = load_limit_list(ll_start, end_date)
        log.info(f"limit_list 合计 upserted: {total} rows")


def main():
    parser = argparse.ArgumentParser(description="StockDB 全量历史数据初始化")
    parser.add_argument("--start",  default=INIT_START_DATE, help="起始日期 YYYYMMDD")
    parser.add_argument("--end",    default=today_str(),     help="结束日期 YYYYMMDD")
    parser.add_argument("--tables", default=",".join(LOAD_ORDER),
                        help="逗号分隔的表名列表（默认全部）")
    args = parser.parse_args()

    start_date = args.start
    end_date   = args.end
    tables     = [t.strip() for t in args.tables.split(",")]

    log.info(f"初始化加载: {start_date} ~ {end_date}")
    log.info(f"目标表: {tables}")

    # 先获取交易日列表（需要 trade_calendar 已存在）
    # 如果 trade_calendar 不存在，先加载它
    if "trade_calendar" in tables:
        from stockdb.loaders.trade_calendar import load_trade_calendar
        load_trade_calendar(start_date, end_date)
        tables = [t for t in tables if t != "trade_calendar"]

    trade_dates = get_trade_dates(start_date, end_date)
    log.info(f"共 {len(trade_dates)} 个交易日")

    overall_start = datetime.now()
    for table in tables:
        if table not in LOAD_ORDER:
            log.warning(f"未知表: {table}，跳过")
            continue
        t_start = datetime.now()
        try:
            load_table(table, trade_dates, start_date, end_date)
        except Exception as e:
            log.error(f"{table} 加载过程中断: {e}")
        elapsed = (datetime.now() - t_start).seconds / 60
        log.info(f"{table} 耗时 {elapsed:.1f} 分钟")

    total_elapsed = (datetime.now() - overall_start).seconds / 60
    log.info(f"\n全部完成！总耗时 {total_elapsed:.1f} 分钟")


if __name__ == "__main__":
    main()
