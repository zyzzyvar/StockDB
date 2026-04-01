"""
Baostock 数据获取层（5分钟K线）

Baostock 使用 TCP socket 协议，不受 macOS SSL 问题影响。
无需注册，匿名 login 即可使用。
"""
import atexit
import time
from datetime import datetime
import pandas as pd

from stockdb.config import BAOSTOCK_INTERVAL
from stockdb.utils.logger import log


# ── Baostock 生命周期 ─────────────────────────────────────────
_bs_logged_in = False


def _ensure_login():
    global _bs_logged_in
    if not _bs_logged_in:
        import baostock as bs
        lg = bs.login()
        if lg.error_code != '0':
            raise RuntimeError(f"Baostock login 失败: {lg.error_msg}")
        _bs_logged_in = True
        atexit.register(_logout)
        log.debug("Baostock login 成功")


def _logout():
    global _bs_logged_in
    if _bs_logged_in:
        import baostock as bs
        bs.logout()
        _bs_logged_in = False


def _sleep():
    time.sleep(BAOSTOCK_INTERVAL)


# ── 代码格式转换 ──────────────────────────────────────────────

def _to_bs_code(ts_code: str) -> str:
    """600000.SH → sh.600000，000001.SZ → sz.000001"""
    symbol, exchange = ts_code.split('.')
    return f"{exchange.lower()}.{symbol}"


def _parse_time(time_str: str):
    """
    Baostock time 列格式：'20240101093500000'（17位，YYYYMMDDHHMMSSmmm）
    提取 HH:MM:SS → datetime.time，解析失败返回 None
    """
    if not time_str or len(time_str) < 14:
        return None
    try:
        return datetime.strptime(time_str[8:14], "%H%M%S").time()
    except ValueError:
        return None


# ── 5分钟K线 ─────────────────────────────────────────────────

def fetch_minute_5min(ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    获取单只股票的5分钟K线（不复权）。

    Parameters
    ----------
    ts_code    : StockDB 格式，如 '600000.SH'
    start_date : YYYYMMDD
    end_date   : YYYYMMDD

    Returns
    -------
    DataFrame 列：ts_code, trade_date, trade_time, open, high, low, close, vol, amount
    vol 单位：股（与 baostock 原始一致）
    """
    import baostock as bs
    _ensure_login()

    bs_code = _to_bs_code(ts_code)
    # baostock 日期格式：YYYY-MM-DD
    start = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:]}"
    end   = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:]}"

    rs = bs.query_history_k_data_plus(
        code=bs_code,
        fields="date,time,code,open,high,low,close,volume,amount,adjustflag",
        start_date=start,
        end_date=end,
        frequency="5",
        adjustflag="3",  # 不复权
    )
    _sleep()

    if rs.error_code != '0':
        log.warning(f"baostock {ts_code} {start}~{end}: {rs.error_msg}")
        return pd.DataFrame()

    data = []
    while rs.next():
        data.append(rs.get_row_data())

    if not data:
        return pd.DataFrame()

    df = pd.DataFrame(data, columns=rs.fields)

    # 过滤空行（非交易时段 baostock 有时会返回空值行）
    df = df[df["open"].str.strip() != ""].copy()
    if df.empty:
        return pd.DataFrame()

    # 类型转换
    df["ts_code"]    = ts_code
    df["trade_date"] = pd.to_datetime(df["date"], format="%Y-%m-%d").dt.date
    df["trade_time"] = df["time"].apply(_parse_time)
    df["open"]       = pd.to_numeric(df["open"],   errors="coerce")
    df["high"]       = pd.to_numeric(df["high"],   errors="coerce")
    df["low"]        = pd.to_numeric(df["low"],    errors="coerce")
    df["close"]      = pd.to_numeric(df["close"],  errors="coerce")
    df["vol"]        = pd.to_numeric(df["volume"], errors="coerce").apply(
        lambda x: int(x) if pd.notna(x) else None
    )
    df["amount"]     = pd.to_numeric(df["amount"], errors="coerce")

    # 过滤无效时间（如解析失败的行）
    df = df[df["trade_time"].notna()].copy()

    return df[["ts_code", "trade_date", "trade_time",
               "open", "high", "low", "close", "vol", "amount"]]
