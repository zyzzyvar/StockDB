"""
美股数据获取（yfinance + NASDAQ Trader）。

数据源（全部免费，无需 API key）：
  - 股票池：nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt + otherlisted.txt
  - 行情：  yfinance（日线 + 5 分钟 K 线，intraday 限近 60 天）
  - 日历：  pandas_market_calendars（NYSE，含节假日/半日市/DST）
"""
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import io
import ssl
import urllib.request

import pandas as pd
import yfinance as yf
import pandas_market_calendars as mcal

from stockdb.config import US_YF_CHUNK_SIZE, US_YF_CHUNK_SLEEP, NASDAQ_TRADER_BASE
from stockdb.utils.logger import log
from stockdb.utils.retry import api_retry

# macOS 系统 Python 有时缺少 CA bundle，对 NASDAQ Trader 禁用 SSL 验证
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

ET = ZoneInfo("America/New_York")

_EXCHANGE_MAP = {"A": "NYSE MKT", "N": "NYSE", "P": "NYSE ARCA", "Z": "BATS", "Q": "NASDAQ"}


def _sleep(secs: float = US_YF_CHUNK_SLEEP):
    time.sleep(secs)


# ── 1. 股票池（NASDAQ Trader 官方符号文件）─────────────────────────────

@api_retry()
def fetch_us_symbols() -> pd.DataFrame:
    """
    从 NASDAQ Trader 下载全市场符号列表。
    返回列：ts_code, symbol, yf_symbol, name, exchange, security_type, is_etf, list_status
    约 8-11k 行（含 ETF）。
    """
    nasdaq_url = f"{NASDAQ_TRADER_BASE}/nasdaqlisted.txt"
    other_url  = f"{NASDAQ_TRADER_BASE}/otherlisted.txt"

    def _fetch_pipe_file(url: str) -> str:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, context=_SSL_CTX, timeout=30) as resp:
            return resp.read().decode("utf-8")

    # ── NASDAQ 上市股票 ────────────────────────────────────────────────
    try:
        raw = _fetch_pipe_file(nasdaq_url)
        df_nasdaq = pd.read_csv(io.StringIO(raw), sep="|", dtype=str)
        df_nasdaq = df_nasdaq[df_nasdaq["Symbol"].notna()]
        df_nasdaq = df_nasdaq[~df_nasdaq["Symbol"].str.startswith("File Creation Time")]
        df_nasdaq = df_nasdaq[df_nasdaq["Test Issue"] == "N"]
        df_nasdaq = df_nasdaq.rename(columns={"Symbol": "symbol", "Security Name": "name", "ETF": "etf_flag"})
        df_nasdaq["exchange"] = "NASDAQ"
        df_nasdaq = df_nasdaq[["symbol", "name", "exchange", "etf_flag"]].copy()
    except Exception as e:
        log.error(f"NASDAQ Trader nasdaqlisted.txt 获取失败: {e}")
        df_nasdaq = pd.DataFrame(columns=["symbol", "name", "exchange", "etf_flag"])

    # ── 其他交易所（NYSE / ARCA / BATS 等）────────────────────────────
    try:
        raw = _fetch_pipe_file(other_url)
        df_other = pd.read_csv(io.StringIO(raw), sep="|", dtype=str)
        df_other = df_other[df_other["ACT Symbol"].notna()]
        df_other = df_other[~df_other["ACT Symbol"].str.startswith("File Creation Time")]
        df_other = df_other[df_other["Test Issue"] == "N"]
        df_other = df_other.rename(columns={"ACT Symbol": "symbol", "Security Name": "name",
                                             "Exchange": "exchange_code", "ETF": "etf_flag"})
        df_other["exchange"] = df_other["exchange_code"].map(_EXCHANGE_MAP).fillna("OTHER")
        df_other = df_other[["symbol", "name", "exchange", "etf_flag"]].copy()
    except Exception as e:
        log.error(f"NASDAQ Trader otherlisted.txt 获取失败: {e}")
        df_other = pd.DataFrame(columns=["symbol", "name", "exchange", "etf_flag"])

    df = pd.concat([df_nasdaq, df_other], ignore_index=True)

    # ── 派生字段 ────────────────────────────────────────────────────────
    df["yf_symbol"]     = df["symbol"].str.replace(".", "-", regex=False)
    df["ts_code"]       = df["yf_symbol"] + ".US"
    df["is_etf"]        = (df["etf_flag"].str.upper() == "Y").astype(int)
    df["security_type"] = df["is_etf"].map({1: "ETF", 0: "CS"})
    df["list_status"]   = "L"
    df["updated_at"]    = datetime.now()
    df["name"]          = df["name"].str[:120]

    # 去重（NASDAQ 文件和 other 文件可能重叠）——优先保留 NASDAQ 行
    df = df.drop_duplicates(subset="ts_code", keep="first")
    df = df[["ts_code", "symbol", "yf_symbol", "name", "exchange",
             "security_type", "is_etf", "list_status", "updated_at"]]

    log.info(f"fetch_us_symbols: {len(df)} symbols (含 ETF)")
    return df


# ── 2. 交易日历（pandas_market_calendars / NYSE）────────────────────────

def fetch_us_trade_calendar(start_date: str, end_date: str) -> pd.DataFrame:
    """
    生成 NYSE 交易日历。
    返回列：cal_date, is_open, pretrade_date, is_early_close, market_close_et, exchange
    """
    nyse = mcal.get_calendar("XNYS")

    # 全日历天范围
    start = pd.Timestamp(f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:]}")
    end   = pd.Timestamp(f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:]}")
    all_days = pd.date_range(start, end, freq="D")

    # 开市日程（含市场开收盘时间）
    try:
        sched = nyse.schedule(start_date=start.date(), end_date=end.date())
    except Exception:
        sched = pd.DataFrame()

    open_days = set(sched.index.date) if not sched.empty else set()

    rows = []
    prev_open = None
    for day in all_days:
        d = day.date()
        is_open = 1 if d in open_days else 0

        market_close_et = None
        is_early_close  = 0
        if is_open and not sched.empty and d in open_days:
            close_utc = sched.loc[pd.Timestamp(d), "market_close"]
            close_et  = close_utc.tz_convert("America/New_York")
            market_close_et = close_et.time().replace(tzinfo=None)
            # 正常收盘 16:00 ET；早收盘（半日市）< 16:00
            if close_et.hour < 16:
                is_early_close = 1

        rows.append({
            "cal_date":        d,
            "is_open":         is_open,
            "pretrade_date":   prev_open,
            "is_early_close":  is_early_close,
            "market_close_et": market_close_et,
            "exchange":        "NYSE",
        })
        if is_open:
            prev_open = d

    df = pd.DataFrame(rows)
    log.info(f"fetch_us_trade_calendar: {len(df)} days, {df['is_open'].sum()} open ({start_date}~{end_date})")
    return df


# ── 3. 日线行情（yfinance 批量）──────────────────────────────────────────

def _reshape_yf_daily(raw, yf_to_ts: dict) -> pd.DataFrame:
    """将 yf.download 宽格式转为长格式 DataFrame，列名映射到 DB 字段。

    yfinance 1.x 列格式：MultiIndex levels=['Ticker','Price']，即 (ticker, field)。
    使用 level names 来定位 Ticker 维度，避免因版本差异导致 level 索引错乱。
    """
    if raw is None or raw.empty:
        return pd.DataFrame()

    cols = raw.columns
    long_rows = []

    if isinstance(cols, pd.MultiIndex):
        names = list(cols.names)
        ticker_level = names.index("Ticker") if "Ticker" in names else 0
        tickers = cols.get_level_values(ticker_level).unique()

        for ticker in tickers:
            ts_code = yf_to_ts.get(ticker)
            if ts_code is None:
                continue
            try:
                sub = raw.xs(ticker, axis=1, level=ticker_level).copy()
                sub = sub.dropna(how="all")
                if sub.empty:
                    continue
                sub = sub.rename(columns={
                    "Open": "open", "High": "high", "Low": "low",
                    "Close": "close", "Adj Close": "adj_close", "Volume": "vol",
                })
                sub["ts_code"]    = ts_code
                sub["trade_date"] = pd.to_datetime(sub.index).date
                sub["vol"]        = sub["vol"].astype("Int64")
                sub["amount"]     = None
                long_rows.append(sub)
            except Exception as e:
                log.warning(f"_reshape_yf_daily {ticker}: {e}")
    else:
        # 单列层（不应发生，防御处理）
        for ticker, ts_code in yf_to_ts.items():
            try:
                sub = raw.copy().dropna(how="all")
                if sub.empty:
                    continue
                sub = sub.rename(columns={
                    "Open": "open", "High": "high", "Low": "low",
                    "Close": "close", "Adj Close": "adj_close", "Volume": "vol",
                })
                sub["ts_code"]    = ts_code
                sub["trade_date"] = pd.to_datetime(sub.index).date
                sub["vol"]        = sub["vol"].astype("Int64")
                sub["amount"]     = None
                long_rows.append(sub)
                break
            except Exception as e:
                log.warning(f"_reshape_yf_daily flat {ticker}: {e}")

    if not long_rows:
        return pd.DataFrame()
    return pd.concat(long_rows, ignore_index=True)


def fetch_us_daily_batch(yf_symbols: list, start_date: str, end_date: str) -> pd.DataFrame:
    """
    批量下载美股日线（yfinance）。
    yfinance end 为不含当日，我们对外 API end 为含当日，内部 +1 天。
    返回列：ts_code, trade_date, open, high, low, close, adj_close, vol, amount
    （pre_close/change/pct_chg 由 loader 计算）
    """
    if not yf_symbols:
        return pd.DataFrame()

    start_dt = datetime.strptime(start_date, "%Y%m%d").date()
    end_dt   = datetime.strptime(end_date,   "%Y%m%d").date() + timedelta(days=1)
    yf_start = start_dt.strftime("%Y-%m-%d")
    yf_end   = end_dt.strftime("%Y-%m-%d")

    # 建 yf_symbol → ts_code 映射
    yf_to_ts = {s: f"{s}.US" for s in yf_symbols}

    chunks = [yf_symbols[i:i + US_YF_CHUNK_SIZE]
              for i in range(0, len(yf_symbols), US_YF_CHUNK_SIZE)]
    results = []
    for i, chunk in enumerate(chunks):
        try:
            raw = yf.download(
                tickers=" ".join(chunk),
                start=yf_start,
                end=yf_end,
                interval="1d",
                group_by="ticker",
                auto_adjust=False,
                threads=True,
                progress=False,
            )
            chunk_map = {s: f"{s}.US" for s in chunk}
            part = _reshape_yf_daily(raw, chunk_map)
            if not part.empty:
                results.append(part)
        except Exception as e:
            log.warning(f"fetch_us_daily_batch chunk {i} ({chunk[:3]}...): {e}")
        if i < len(chunks) - 1:
            _sleep()

    if not results:
        return pd.DataFrame()

    df = pd.concat(results, ignore_index=True)
    keep = ["ts_code", "trade_date", "open", "high", "low", "close", "adj_close", "vol", "amount"]
    for c in keep:
        if c not in df.columns:
            df[c] = None
    return df[keep]


# ── 4. 5 分钟 K 线（yfinance 批量）──────────────────────────────────────

def fetch_us_minute_5min_batch(yf_symbols: list, start_date: str, end_date: str) -> pd.DataFrame:
    """
    批量下载美股 5 分钟 K 线（yfinance，仅支持近 60 天）。
    trade_time 存储为 ET 墙钟时间（非 UTC）。
    返回列：ts_code, trade_date, trade_time, open, high, low, close, vol, amount
    """
    if not yf_symbols:
        return pd.DataFrame()

    # 强制 clamp 60 天窗口
    today = date.today()
    floor = today - timedelta(days=59)
    start_dt = max(datetime.strptime(start_date, "%Y%m%d").date(), floor)
    end_dt   = datetime.strptime(end_date, "%Y%m%d").date() + timedelta(days=1)
    if start_dt > end_dt:
        log.warning("fetch_us_minute_5min_batch: 请求范围超过 60 天 intraday 限制，已 clamp")
        return pd.DataFrame()

    yf_start = start_dt.strftime("%Y-%m-%d")
    yf_end   = end_dt.strftime("%Y-%m-%d")

    chunks = [yf_symbols[i:i + US_YF_CHUNK_SIZE]
              for i in range(0, len(yf_symbols), US_YF_CHUNK_SIZE)]
    results = []

    for i, chunk in enumerate(chunks):
        try:
            raw = yf.download(
                tickers=" ".join(chunk),
                start=yf_start,
                end=yf_end,
                interval="5m",
                group_by="ticker",
                auto_adjust=False,
                threads=True,
                progress=False,
            )
            if raw is None or raw.empty:
                continue

            cols = raw.columns
            if isinstance(cols, pd.MultiIndex):
                names = list(cols.names)
                ticker_level = names.index("Ticker") if "Ticker" in names else 0
                tickers = cols.get_level_values(ticker_level).unique()
            else:
                ticker_level = None
                tickers = chunk

            for ticker in tickers:
                ts_code = f"{ticker}.US"
                try:
                    sub = (raw.xs(ticker, axis=1, level=ticker_level).copy()
                           if ticker_level is not None else raw.copy())
                    sub = sub.dropna(how="all")
                    if sub.empty:
                        continue
                    # 索引转 ET 时区
                    idx = pd.DatetimeIndex(sub.index)
                    if idx.tz is None:
                        idx = idx.tz_localize("UTC")
                    idx_et = idx.tz_convert("America/New_York")
                    sub.index = idx_et
                    sub["ts_code"]    = ts_code
                    sub["trade_date"] = idx_et.date
                    sub["trade_time"] = idx_et.time
                    sub = sub.rename(columns={
                        "Open": "open", "High": "high", "Low": "low",
                        "Close": "close", "Volume": "vol",
                    })
                    sub["amount"] = None
                    sub["vol"]    = sub["vol"].astype("Int64")
                    keep = ["ts_code", "trade_date", "trade_time",
                            "open", "high", "low", "close", "vol", "amount"]
                    results.append(sub[[c for c in keep if c in sub.columns]])
                except Exception as e:
                    log.warning(f"fetch_us_minute_5min_batch {ticker}: {e}")
        except Exception as e:
            log.warning(f"fetch_us_minute_5min_batch chunk {i}: {e}")
        if i < len(chunks) - 1:
            _sleep()

    if not results:
        return pd.DataFrame()
    return pd.concat(results, ignore_index=True)
