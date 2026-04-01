"""每日基本面指标加载"""
from datetime import datetime
from typing import List
from stockdb.fetchers.tushare_fetcher import fetch_daily_basic_by_date
from stockdb.loaders.base import upsert_dataframe, log_update, already_updated
from stockdb.utils.logger import log

TABLE = "daily_fundamental"
UPDATE_COLS = [
    "close", "turnover_rate", "turnover_rate_f", "volume_ratio",
    "pe", "pe_ttm", "pb", "ps", "ps_ttm",
    "dv_ratio", "dv_ttm",
    "total_share", "float_share", "free_share", "total_mv", "circ_mv",
]


def load_daily_fundamental_by_date(trade_date_str: str) -> int:
    td = datetime.strptime(trade_date_str, "%Y%m%d").date()
    started = datetime.now()
    try:
        df = fetch_daily_basic_by_date(trade_date_str)
        if df.empty:
            return 0
        n = upsert_dataframe(df, TABLE,
                             conflict_cols=["ts_code", "trade_date"],
                             update_cols=UPDATE_COLS)
        log.info(f"daily_fundamental {trade_date_str}: upserted {n} rows")
        log_update(TABLE, "incremental", trade_date=td,
                   rows_upserted=n, status="success", started_at=started)
        return n
    except Exception as e:
        log.error(f"daily_fundamental {trade_date_str} 加载失败: {e}")
        log_update(TABLE, "incremental", trade_date=td,
                   status="failed", error_msg=str(e), started_at=started)
        raise


def load_daily_fundamental_batch(trade_dates: List[str], skip_existing: bool = True) -> int:
    total = 0
    for td_str in trade_dates:
        td = datetime.strptime(td_str, "%Y%m%d").date()
        if skip_existing and already_updated(TABLE, td):
            continue
        try:
            total += load_daily_fundamental_by_date(td_str)
        except Exception as e:
            log.error(f"daily_fundamental {td_str}: 跳过（{e}）")
    return total
