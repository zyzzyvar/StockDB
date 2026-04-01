"""复权因子加载"""
from datetime import datetime
from typing import List
from sqlalchemy import text
from stockdb.fetchers.tushare_fetcher import fetch_adj_factor, fetch_adj_factor_by_date
from stockdb.loaders.base import upsert_dataframe, log_update, already_updated
from stockdb.db import engine
from stockdb.utils.logger import log

TABLE = "adj_factor"


def load_adj_factor_by_date(trade_date_str: str) -> int:
    """按交易日加载全市场复权因子（一次 API 调用）"""
    td = datetime.strptime(trade_date_str, "%Y%m%d").date()
    started = datetime.now()
    try:
        df = fetch_adj_factor_by_date(trade_date_str)
        n = 0
        if not df.empty:
            n = upsert_dataframe(df, TABLE,
                                 conflict_cols=["ts_code", "trade_date"],
                                 update_cols=["adj_factor"])
        log.info(f"adj_factor {trade_date_str}: upserted {n} rows")
        log_update(TABLE, "incremental", trade_date=td,
                   rows_upserted=n, status="success", started_at=started)
        return n
    except Exception as e:
        log.error(f"adj_factor {trade_date_str} 加载失败: {e}")
        log_update(TABLE, "incremental", trade_date=td,
                   status="failed", error_msg=str(e), started_at=started)
        raise


def load_adj_factor_for_codes(ts_codes: List[str],
                               start_date: str = None,
                               end_date: str = None) -> int:
    """批量加载多只股票的复权因子"""
    started = datetime.now()
    total = 0
    failed = []
    for ts_code in ts_codes:
        try:
            df = fetch_adj_factor(ts_code, start_date, end_date)
            if df.empty:
                continue
            n = upsert_dataframe(df, TABLE,
                                 conflict_cols=["ts_code", "trade_date"],
                                 update_cols=["adj_factor"])
            total += n
        except Exception as e:
            log.error(f"adj_factor {ts_code}: {e}")
            failed.append(ts_code)

    log.info(f"adj_factor: upserted {total} rows, {len(failed)} failed")
    if failed:
        log.warning(f"adj_factor 失败列表: {failed[:20]}")
    log_update(TABLE, "incremental" if start_date else "full",
               rows_upserted=total, status="success", started_at=started)
    return total


def get_all_ts_codes() -> List[str]:
    """从 stock_basic 取所有上市中股票的 ts_code"""
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT ts_code FROM stock_basic WHERE list_status = 'L'")
        ).fetchall()
    return [r[0] for r in rows]


def repair_recent_adj_factors(days: int = 30) -> int:
    """
    修复近 N 天的复权因子（分红送股后复权因子会追溯修改）。
    建议每周运行一次。
    """
    from stockdb.utils.date_utils import today_str, str_to_date
    from datetime import timedelta
    end = today_str()
    start = (str_to_date(end) - timedelta(days=days)).strftime("%Y%m%d")
    ts_codes = get_all_ts_codes()
    log.info(f"repair adj_factor: {len(ts_codes)} stocks, {start}~{end}")
    return load_adj_factor_for_codes(ts_codes, start_date=start, end_date=end)
