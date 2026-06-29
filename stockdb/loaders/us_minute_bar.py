"""美股5分钟K线加载（yfinance）"""
from datetime import datetime
from stockdb.fetchers.us_fetcher import fetch_us_minute_5min_batch
from stockdb.loaders.base import bulk_upsert_dataframe, log_update
from stockdb.utils.logger import log

TABLE         = "us_minute_bar_5min"
CONFLICT_COLS = ["ts_code", "trade_date", "trade_time"]
UPDATE_COLS   = ["open", "high", "low", "close", "vol", "amount"]


def load_us_minute_5min_by_codes(yf_symbols: list, start_date: str, end_date: str) -> int:
    """加载指定符号列表的5分钟K线。不写 data_update_log（供回补使用）。"""
    if not yf_symbols:
        return 0
    df = fetch_us_minute_5min_batch(yf_symbols, start_date, end_date)
    if df.empty:
        return 0
    n = bulk_upsert_dataframe(df, TABLE, CONFLICT_COLS, UPDATE_COLS)
    log.debug(f"us_minute_bar_5min {start_date}~{end_date} ({len(yf_symbols)} symbols): {n} rows")
    return n


def load_us_minute_5min_daily(trade_date_str: str) -> int:
    """
    加载单个已收盘美股交易日的全市场5分钟K线（每日增量用）。
    全市场约 8-11k 只，yfinance 按 chunk 拉取。
    写入一条 data_update_log（success 或 partial）。
    """
    from stockdb.loaders.us_stock_basic import get_us_yf_symbols
    from stockdb.config import US_YF_CHUNK_SIZE

    td = datetime.strptime(trade_date_str, "%Y%m%d").date()
    started = datetime.now()

    yf_symbols = get_us_yf_symbols()
    if not yf_symbols:
        log.warning("us_minute_bar_5min: 股票池为空，请先运行 load_us_stock_basic()")
        return 0

    total  = 0
    failed = []

    chunks = [yf_symbols[i:i + US_YF_CHUNK_SIZE]
              for i in range(0, len(yf_symbols), US_YF_CHUNK_SIZE)]

    for chunk in chunks:
        try:
            df = fetch_us_minute_5min_batch(chunk, trade_date_str, trade_date_str)
            if df.empty:
                continue
            # 只保留目标日（避免跨日污染）
            df = df[df["trade_date"] == td]
            if df.empty:
                continue
            n = bulk_upsert_dataframe(df, TABLE, CONFLICT_COLS, UPDATE_COLS)
            total += n
        except Exception as e:
            log.warning(f"us_minute_bar_5min {trade_date_str} chunk: {e}")
            failed.extend(chunk)

    status = "success" if not failed else "partial"
    log.info(f"us_minute_bar_5min {trade_date_str}: {total} rows, {len(failed)} symbols failed")
    log_update(TABLE, "incremental", trade_date=td,
               rows_upserted=total, status=status, started_at=started,
               error_msg=f"{len(failed)} symbols failed" if failed else None)
    return total
