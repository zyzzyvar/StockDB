"""龙虎榜加载"""
from datetime import datetime
from typing import List
from stockdb.fetchers.tushare_fetcher import fetch_top_list
from stockdb.loaders.base import upsert_dataframe, log_update, already_updated
from stockdb.utils.logger import log

TABLE = "top_list"
UPDATE_COLS = [
    "name", "close", "pct_change", "turnover_rate", "amount",
    "l_buy", "l_sell", "l_amount", "net_amount", "net_rate",
    "amount_rate", "float_values", "reason",
]


def load_top_list_by_date(trade_date_str: str) -> int:
    td = datetime.strptime(trade_date_str, "%Y%m%d").date()
    started = datetime.now()
    try:
        df = fetch_top_list(trade_date_str)
        n = 0
        if not df.empty:
            n = upsert_dataframe(df, TABLE,
                                 conflict_cols=["trade_date", "ts_code"],
                                 update_cols=UPDATE_COLS)
        log.info(f"top_list {trade_date_str}: upserted {n} rows")
        log_update(TABLE, "incremental", trade_date=td,
                   rows_upserted=n, status="success", started_at=started)
        return n
    except Exception as e:
        log.error(f"top_list {trade_date_str} 加载失败: {e}")
        log_update(TABLE, "incremental", trade_date=td,
                   status="failed", error_msg=str(e), started_at=started)
        raise


def load_top_list_batch(trade_dates: List[str], skip_existing: bool = True) -> int:
    total = 0
    for td_str in trade_dates:
        td = datetime.strptime(td_str, "%Y%m%d").date()
        if skip_existing and already_updated(TABLE, td):
            continue
        try:
            total += load_top_list_by_date(td_str)
        except Exception as e:
            log.error(f"top_list {td_str}: 跳过（{e}）")
    return total
