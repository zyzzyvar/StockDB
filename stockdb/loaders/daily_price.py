"""日线行情加载"""
from datetime import datetime, date
from typing import List
import pandas as pd
from stockdb.fetchers.tushare_fetcher import fetch_daily_price_by_date
from stockdb.loaders.base import upsert_dataframe, log_update, already_updated
from stockdb.utils.logger import log

TABLE = "daily_price"
CONFLICT_COLS = ["ts_code", "trade_date"]
UPDATE_COLS   = ["open", "high", "low", "close", "pre_close",
                 "change", "pct_chg", "vol", "amount"]


def load_daily_price_by_date(trade_date_str: str) -> int:
    """加载单个交易日的全市场日线行情"""
    td = datetime.strptime(trade_date_str, "%Y%m%d").date()
    started = datetime.now()
    try:
        df = fetch_daily_price_by_date(trade_date_str)
        if df.empty:
            log.info(f"daily_price {trade_date_str}: 无数据（非交易日或停牌）")
            return 0
        n = upsert_dataframe(df, TABLE, CONFLICT_COLS, UPDATE_COLS)
        log.info(f"daily_price {trade_date_str}: upserted {n} rows")
        log_update(TABLE, "incremental", trade_date=td,
                   rows_upserted=n, status="success", started_at=started)
        return n
    except Exception as e:
        log.error(f"daily_price {trade_date_str} 加载失败: {e}")
        log_update(TABLE, "incremental", trade_date=td,
                   status="failed", error_msg=str(e), started_at=started)
        raise


def load_daily_price_batch(trade_dates: List[str], skip_existing: bool = True) -> int:
    """批量加载多个交易日的日线行情（带断点续传）"""
    total = 0
    for td_str in trade_dates:
        td = datetime.strptime(td_str, "%Y%m%d").date()
        if skip_existing and already_updated(TABLE, td):
            log.debug(f"daily_price {td_str}: 已存在，跳过")
            continue
        try:
            total += load_daily_price_by_date(td_str)
        except Exception as e:
            log.error(f"daily_price {td_str}: 跳过（{e}）")
            continue
    return total
