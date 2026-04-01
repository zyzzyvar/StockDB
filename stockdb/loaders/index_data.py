"""指数基本信息及日线加载"""
from datetime import datetime
from typing import List
from stockdb.fetchers.tushare_fetcher import fetch_index_basic, fetch_index_daily
from stockdb.loaders.base import upsert_dataframe, log_update
from stockdb.config import TRACKED_INDICES
from stockdb.utils.date_utils import split_date_range
from stockdb.utils.logger import log


def load_index_basic() -> int:
    started = datetime.now()
    df = fetch_index_basic()
    if df.empty:
        return 0
    n = upsert_dataframe(df, "index_basic",
                         conflict_cols=["ts_code"],
                         update_cols=["name", "market", "category",
                                      "base_date", "base_point", "list_date", "exp_date"])
    log.info(f"index_basic: upserted {n} rows")
    log_update("index_basic", "full", rows_upserted=n, status="success", started_at=started)
    return n


def load_index_daily(start_date: str, end_date: str,
                     ts_codes: List[str] = None, use_fallback: bool = False) -> int:
    """
    加载指数日线行情。
    use_fallback=True 时使用 AKShare（Tushare 失败时备用）。
    """
    if ts_codes is None:
        ts_codes = TRACKED_INDICES

    UPDATE_COLS = ["open", "high", "low", "close", "pre_close",
                   "change", "pct_chg", "vol", "amount"]
    total = 0
    started = datetime.now()

    for ts_code in ts_codes:
        for seg_start, seg_end in split_date_range(start_date, end_date, batch_days=3650):
            try:
                if use_fallback:
                    from stockdb.fetchers.akshare_fetcher import fetch_index_daily_ak
                    df = fetch_index_daily_ak(ts_code, seg_start, seg_end)
                else:
                    df = fetch_index_daily(ts_code, seg_start, seg_end)
                if df.empty:
                    continue
                n = upsert_dataframe(df, "index_daily",
                                     conflict_cols=["ts_code", "trade_date"],
                                     update_cols=UPDATE_COLS)
                total += n
            except Exception as e:
                log.error(f"index_daily {ts_code} {seg_start}~{seg_end}: {e}")

    log.info(f"index_daily: upserted {total} rows")
    log_update("index_daily", "full" if start_date < "20200101" else "incremental",
               rows_upserted=total, status="success", started_at=started)
    return total
