"""美股日线行情加载（yfinance）"""
from datetime import datetime, timedelta
import pandas as pd
from stockdb.fetchers.us_fetcher import fetch_us_daily_batch
from stockdb.loaders.base import bulk_upsert_dataframe, log_update
from stockdb.utils.logger import log

TABLE         = "us_daily_price"
CONFLICT_COLS = ["ts_code", "trade_date"]
UPDATE_COLS   = ["open", "high", "low", "close", "adj_close",
                 "pre_close", "change", "pct_chg", "vol", "amount"]


def _compute_price_changes(df: pd.DataFrame) -> pd.DataFrame:
    """按 ts_code 计算 pre_close / change / pct_chg（需 df 已含多日数据且按日期排序）"""
    df = df.sort_values(["ts_code", "trade_date"]).copy()
    df["pre_close"] = df.groupby("ts_code")["close"].shift(1)
    df["change"]    = df["close"] - df["pre_close"]
    df["pct_chg"]   = (df["change"] / df["pre_close"] * 100).round(4)
    return df


def load_us_daily_by_codes(yf_symbols: list, start_date: str, end_date: str) -> int:
    """
    按符号批量加载日线（回补用）。不写 data_update_log，upsert 幂等。
    内部使用 bulk_upsert 提升写入速度。
    """
    if not yf_symbols:
        return 0

    df = fetch_us_daily_batch(yf_symbols, start_date, end_date)
    if df.empty:
        return 0

    df = _compute_price_changes(df)
    cols = ["ts_code", "trade_date"] + UPDATE_COLS
    df = df[[c for c in cols if c in df.columns]]
    n = bulk_upsert_dataframe(df, TABLE, CONFLICT_COLS, UPDATE_COLS)
    log.info(f"us_daily_price batch {start_date}~{end_date} ({len(yf_symbols)} symbols): {n} rows")
    return n


def load_us_daily_price_by_date(trade_date_str: str) -> int:
    """
    加载单个已收盘美股交易日的全市场日线（每日增量用）。
    拉取目标日前 5 个自然日的数据以计算 pre_close，仅 upsert 目标日。
    写入一条 data_update_log（success 或 partial）。
    """
    from stockdb.loaders.us_stock_basic import get_us_yf_symbols, get_us_ts_code_map
    from stockdb.config import US_YF_CHUNK_SIZE

    td = datetime.strptime(trade_date_str, "%Y%m%d").date()
    started = datetime.now()

    yf_symbols = get_us_yf_symbols()
    if not yf_symbols:
        log.warning("us_daily_price: 股票池为空，请先运行 load_us_stock_basic()")
        return 0

    # 拉取含 5 天前缀以计算 pre_close
    lookback_start = (td - timedelta(days=7)).strftime("%Y%m%d")
    total  = 0
    failed = []

    chunks = [yf_symbols[i:i + US_YF_CHUNK_SIZE]
              for i in range(0, len(yf_symbols), US_YF_CHUNK_SIZE)]

    for chunk in chunks:
        try:
            df = fetch_us_daily_batch(chunk, lookback_start, trade_date_str)
            if df.empty:
                continue
            df = _compute_price_changes(df)
            # 只保留目标日
            df = df[df["trade_date"] == td]
            if df.empty:
                continue
            cols = ["ts_code", "trade_date"] + UPDATE_COLS
            df = df[[c for c in cols if c in df.columns]]
            n = bulk_upsert_dataframe(df, TABLE, CONFLICT_COLS, UPDATE_COLS)
            total += n
        except Exception as e:
            log.warning(f"us_daily_price {trade_date_str} chunk: {e}")
            failed.extend(chunk)

    status = "success" if not failed else "partial"
    log.info(f"us_daily_price {trade_date_str}: {total} rows, {len(failed)} symbols failed")
    log_update(TABLE, "incremental", trade_date=td,
               rows_upserted=total, status=status, started_at=started,
               error_msg=f"{len(failed)} symbols failed" if failed else None)
    return total
