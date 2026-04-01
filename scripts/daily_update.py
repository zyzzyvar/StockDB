#!/usr/bin/env python3
"""
每日增量更新脚本（收盘后运行，建议 17:30 之后）。

用法：
    python scripts/daily_update.py               # 自动检测最新未更新交易日
    python scripts/daily_update.py --date 20250318  # 强制指定日期
    python scripts/daily_update.py --repair-adj     # 修复近30天复权因子

通过 launchd 或 cron 定时调用（见 README）。
"""
import sys
import argparse
from pathlib import Path
from datetime import datetime, date

sys.path.insert(0, str(Path(__file__).parent.parent))

from stockdb.utils.logger import log
from stockdb.utils.date_utils import get_latest_trade_date, today_str, get_trade_dates
from stockdb.db import engine
from sqlalchemy import text

TABLE_MARGIN = "margin_detail"


def _get_update_rows(table_name: str, trade_date_str: str):
    """查询 data_update_log 中某表某日的 rows_upserted；无记录返回 None"""
    sql = text("""
        SELECT rows_upserted FROM data_update_log
        WHERE table_name = :t AND trade_date = :d AND status = 'success'
        ORDER BY id DESC LIMIT 1
    """)
    td = date.fromisoformat(f"{trade_date_str[:4]}-{trade_date_str[4:6]}-{trade_date_str[6:]}")
    with engine.connect() as conn:
        row = conn.execute(sql, {"t": table_name, "d": td}).fetchone()
    return row[0] if row else None


def get_pending_trade_dates() -> list:
    """
    获取所有已在 trade_calendar 中、但 daily_price 尚未更新的交易日。
    返回最多 30 天（避免补数据过多影响性能）。
    """
    sql = text("""
        SELECT to_char(tc.cal_date, 'YYYYMMDD')
        FROM trade_calendar tc
        WHERE tc.is_open = 1
          AND tc.cal_date <= CURRENT_DATE
          AND NOT EXISTS (
              SELECT 1 FROM data_update_log dul
              WHERE dul.table_name = 'daily_price'
                AND dul.trade_date = tc.cal_date
                AND dul.status = 'success'
          )
        ORDER BY tc.cal_date DESC
        LIMIT 30
    """)
    with engine.connect() as conn:
        rows = conn.execute(sql).fetchall()
    # 返回升序（从老到新处理）
    return [r[0] for r in reversed(rows)]


def get_prev_trade_date(trade_date_str: str) -> str | None:
    """获取指定交易日的上一个交易日"""
    sql = text("""
        SELECT to_char(pretrade_date, 'YYYYMMDD')
        FROM trade_calendar
        WHERE cal_date = :d AND is_open = 1
    """)
    with engine.connect() as conn:
        row = conn.execute(sql, {"d": date.fromisoformat(
            f"{trade_date_str[:4]}-{trade_date_str[4:6]}-{trade_date_str[6:]}")}).fetchone()
    return row[0] if row else None


def update_one_day(trade_date_str: str):
    """更新单个交易日的所有增量数据"""
    log.info(f"{'─'*50}")
    log.info(f"更新交易日: {trade_date_str}")
    log.info(f"{'─'*50}")

    results = {}

    # 1. 日线行情
    try:
        from stockdb.loaders.daily_price import load_daily_price_by_date
        n = load_daily_price_by_date(trade_date_str)
        results["daily_price"] = n
    except Exception as e:
        log.error(f"daily_price {trade_date_str}: {e}")
        results["daily_price"] = -1

    # 2. 每日基本面
    try:
        from stockdb.loaders.daily_fundamental import load_daily_fundamental_by_date
        n = load_daily_fundamental_by_date(trade_date_str)
        results["daily_fundamental"] = n
    except Exception as e:
        log.error(f"daily_fundamental {trade_date_str}: {e}")
        results["daily_fundamental"] = -1

    # 3. 复权因子（按日批量获取全市场，一次调用）
    try:
        from stockdb.loaders.adj_factor import load_adj_factor_by_date
        n = load_adj_factor_by_date(trade_date_str)
        results["adj_factor"] = n
    except Exception as e:
        log.error(f"adj_factor {trade_date_str}: {e}")
        results["adj_factor"] = -1

    # 4. 指数日线
    try:
        from stockdb.loaders.index_data import load_index_daily
        n = load_index_daily(trade_date_str, trade_date_str)
        results["index_daily"] = n
    except Exception as e:
        log.error(f"index_daily {trade_date_str}: {e}")
        results["index_daily"] = -1

    # 5. 资金流向
    try:
        from stockdb.loaders.money_flow import load_money_flow_by_date
        n = load_money_flow_by_date(trade_date_str)
        results["money_flow"] = n
    except Exception as e:
        log.error(f"money_flow {trade_date_str}: {e}")
        results["money_flow"] = -1

    # 6. 融资融券（T+1发布，同时补录上一交易日数据）
    try:
        from stockdb.loaders.margin_detail import load_margin_detail_by_date
        from stockdb.loaders.base import already_updated
        # 补录前一交易日（T+1数据，昨天的今天才能拿到）
        prev_date = get_prev_trade_date(trade_date_str)
        if prev_date:
            prev_log = _get_update_rows(TABLE_MARGIN, prev_date)
            if prev_log is not None and prev_log == 0:
                log.info(f"补录前日融资融券: {prev_date}")
                n_prev = load_margin_detail_by_date(prev_date)
                results[f"margin_detail({prev_date})"] = n_prev
        n = load_margin_detail_by_date(trade_date_str)
        results["margin_detail"] = n
    except Exception as e:
        log.error(f"margin_detail {trade_date_str}: {e}")
        results["margin_detail"] = -1

    # 7. 龙虎榜
    try:
        from stockdb.loaders.top_list import load_top_list_by_date
        n = load_top_list_by_date(trade_date_str)
        results["top_list"] = n
    except Exception as e:
        log.error(f"top_list {trade_date_str}: {e}")
        results["top_list"] = -1

    # 8. 大宗交易
    try:
        from stockdb.loaders.block_trade import load_block_trade_by_date
        n = load_block_trade_by_date(trade_date_str)
        results["block_trade"] = n
    except Exception as e:
        log.error(f"block_trade {trade_date_str}: {e}")
        results["block_trade"] = -1

    # 9. 涨跌停
    try:
        from stockdb.loaders.limit_list import load_limit_list_by_date
        n = load_limit_list_by_date(trade_date_str)
        results["limit_list"] = n
    except Exception as e:
        log.error(f"limit_list {trade_date_str}: {e}")
        results["limit_list"] = -1

    # 汇总
    success = sum(1 for v in results.values() if v >= 0)
    log.info(f"{trade_date_str} 更新完成: {success}/{len(results)} 表成功")
    for k, v in results.items():
        status = f"{v} rows" if v >= 0 else "FAILED"
        log.info(f"  {k}: {status}")


def update_stock_basic():
    """每周一更新股票基本信息（检测新上市/退市）"""
    if date.today().weekday() == 0:  # 周一
        try:
            from stockdb.loaders.stock_basic import load_stock_basic
            n = load_stock_basic()
            log.info(f"stock_basic 周度更新: {n} rows")
        except Exception as e:
            log.error(f"stock_basic 更新失败: {e}")


def update_trade_calendar():
    """更新交易日历到未来一年"""
    try:
        from stockdb.loaders.trade_calendar import load_trade_calendar
        from datetime import timedelta
        end = (date.today().replace(year=date.today().year + 1)).strftime("%Y%m%d")
        load_trade_calendar(today_str(), end)
    except Exception as e:
        log.error(f"trade_calendar 更新失败: {e}")


def main():
    parser = argparse.ArgumentParser(description="StockDB 每日增量更新")
    parser.add_argument("--date",       help="强制指定交易日 YYYYMMDD")
    parser.add_argument("--repair-adj", action="store_true",
                        help="修复近30天复权因子（每周运行一次）")
    args = parser.parse_args()

    log.info(f"StockDB daily_update 启动: {datetime.now():%Y-%m-%d %H:%M:%S}")

    # 修复复权因子
    if args.repair_adj:
        from stockdb.loaders.adj_factor import repair_recent_adj_factors
        repair_recent_adj_factors(days=30)
        return

    # 更新交易日历和股票基本信息
    update_trade_calendar()
    update_stock_basic()

    # 确定要更新的交易日
    if args.date:
        trade_dates = [args.date]
    else:
        trade_dates = get_pending_trade_dates()
        if not trade_dates:
            log.info("没有待更新的交易日，退出")
            return

    log.info(f"待更新交易日: {trade_dates}")

    for td in trade_dates:
        update_one_day(td)

    log.info(f"daily_update 完成: {datetime.now():%Y-%m-%d %H:%M:%S}")


if __name__ == "__main__":
    main()
