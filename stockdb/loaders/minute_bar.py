"""5分钟K线加载（Baostock）"""
from datetime import datetime, date
from typing import List
from stockdb.loaders.base import bulk_upsert_dataframe, log_update, already_updated
from stockdb.utils.logger import log

TABLE         = "minute_bar_5min"
CONFLICT_COLS = ["ts_code", "trade_date", "trade_time"]
UPDATE_COLS   = ["open", "high", "low", "close", "vol", "amount"]


def load_minute_5min_by_code(ts_code: str, start_date: str, end_date: str) -> int:
    """加载单只股票指定日期范围的5分钟K线。不写 data_update_log（用于批量回补）。"""
    from stockdb.fetchers.baostock_fetcher import fetch_minute_5min
    df = fetch_minute_5min(ts_code, start_date, end_date)
    if df.empty:
        return 0
    n = bulk_upsert_dataframe(df, TABLE, CONFLICT_COLS, UPDATE_COLS)
    log.debug(f"minute_bar_5min {ts_code} {start_date}~{end_date}: {n} rows")
    return n


def load_minute_5min_daily(trade_date_str: str) -> int:
    """
    加载单个交易日全市场5分钟K线（每日增量用）。
    迭代所有在市股票，写入 data_update_log。
    约 5490 只 × 0.05s ≈ 5 分钟。
    """
    from stockdb.loaders.adj_factor import get_all_ts_codes
    td = datetime.strptime(trade_date_str, "%Y%m%d").date()
    started = datetime.now()
    ts_codes = get_all_ts_codes()
    total = 0
    failed = []

    for ts_code in ts_codes:
        try:
            n = load_minute_5min_by_code(ts_code, trade_date_str, trade_date_str)
            total += n
        except Exception as e:
            log.warning(f"minute_bar_5min {ts_code} {trade_date_str}: {e}")
            failed.append(ts_code)

    status = "success" if not failed else "partial"
    log.info(f"minute_bar_5min {trade_date_str}: {total} rows, {len(failed)} failed")
    if failed:
        log.warning(f"minute_bar_5min 失败列表: {failed[:10]}")
    log_update(TABLE, "incremental", trade_date=td,
               rows_upserted=total, status=status, started_at=started,
               error_msg=f"{len(failed)} stocks failed" if failed else None)
    return total
