"""
AKShare 数据获取层（备用数据源）
当 Tushare 接口不可用或积分不足时使用。
"""
import time
import akshare as ak
import pandas as pd
from stockdb.utils.logger import log
from stockdb.utils.retry import api_retry


def _sleep(t: float = 0.5):
    time.sleep(t)


@api_retry()
def fetch_daily_price_ak(ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    通过 AKShare 获取个股不复权日线行情。
    ts_code 格式：000001.SZ → symbol=000001, 上交所 .SH → sh+symbol
    """
    symbol = ts_code.split(".")[0]
    exchange = ts_code.split(".")[1]

    if exchange == "SH":
        ak_symbol = f"sh{symbol}"
    elif exchange == "SZ":
        ak_symbol = f"sz{symbol}"
    else:
        ak_symbol = symbol

    df = ak.stock_zh_a_hist(
        symbol=symbol,
        period="daily",
        start_date=start_date[:4] + "-" + start_date[4:6] + "-" + start_date[6:],
        end_date=end_date[:4]   + "-" + end_date[4:6]   + "-" + end_date[6:],
        adjust="",  # 不复权
    )
    _sleep()
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.rename(columns={
        "日期": "trade_date",
        "开盘": "open",
        "最高": "high",
        "最低": "low",
        "收盘": "close",
        "成交量": "vol",
        "成交额": "amount",
        "涨跌幅": "pct_chg",
        "涨跌额": "change",
    })
    df["ts_code"]    = ts_code
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    df["pre_close"]  = (df["close"] - df["change"]).round(4)
    df["vol"]        = df["vol"] / 100  # AKShare 返回股，转换为手

    keep = ["ts_code", "trade_date", "open", "high", "low", "close",
            "pre_close", "change", "pct_chg", "vol", "amount"]
    available = [c for c in keep if c in df.columns]
    return df[available]


@api_retry()
def fetch_index_daily_ak(ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """通过 AKShare 获取指数日线行情"""
    symbol_map = {
        "000001.SH": "sh000001",
        "399001.SZ": "sz399001",
        "399006.SZ": "sz399006",
        "000300.SH": "sh000300",
        "000905.SH": "sh000905",
        "000852.SH": "sh000852",
        "000016.SH": "sh000016",
        "000688.SH": "sh000688",
    }
    ak_code = symbol_map.get(ts_code, ts_code.replace(".SH", "").replace(".SZ", ""))

    df = ak.stock_zh_index_daily(symbol=ak_code)
    _sleep()
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.rename(columns={
        "date": "trade_date",
        "open": "open",
        "high": "high",
        "low":  "low",
        "close": "close",
        "volume": "vol",
    })
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    df["ts_code"]    = ts_code

    sd = pd.to_datetime(start_date, format="%Y%m%d").date()
    ed = pd.to_datetime(end_date,   format="%Y%m%d").date()
    df = df[(df["trade_date"] >= sd) & (df["trade_date"] <= ed)]

    for col in ["pre_close", "change", "pct_chg", "amount"]:
        if col not in df.columns:
            df[col] = None

    keep = ["ts_code", "trade_date", "open", "high", "low", "close",
            "pre_close", "change", "pct_chg", "vol", "amount"]
    available = [c for c in keep if c in df.columns]
    return df[available].reset_index(drop=True)
