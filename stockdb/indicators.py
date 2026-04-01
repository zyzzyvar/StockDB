"""
技术指标计算便捷函数
从数据库读取 OHLCV 数据，计算并返回含指标的 DataFrame。
下游分析应用直接调用这些函数，指标不预存入数据库。

依赖：pandas_ta（pip install pandas-ta）
"""
from datetime import date
from typing import Optional
import pandas as pd
import pandas_ta as ta
from sqlalchemy import text
from stockdb.db import engine


def get_ohlcv(
    ts_code: str,
    start_date: str = None,
    end_date: str = None,
    adjusted: bool = True,
) -> pd.DataFrame:
    """
    获取个股 OHLCV 数据（默认前复权）。

    返回 DataFrame，index 为 trade_date（升序），列：
      open, high, low, close, pre_close, pct_chg, vol, amount
      + adj_factor（若 adjusted=True）

    adjusted=True：使用前复权价（推荐用于技术分析）
    adjusted=False：返回原始不复权价
    """
    date_filter = ""
    params: dict = {"code": ts_code}

    if start_date:
        date_filter += " AND dp.trade_date >= :start"
        params["start"] = pd.to_datetime(start_date, format="%Y%m%d").date()
    if end_date:
        date_filter += " AND dp.trade_date <= :end"
        params["end"] = pd.to_datetime(end_date, format="%Y%m%d").date()

    if adjusted:
        sql = text(f"""
            SELECT
                dp.trade_date,
                dp.open      * af.adj_factor / latest_af.latest AS open,
                dp.high      * af.adj_factor / latest_af.latest AS high,
                dp.low       * af.adj_factor / latest_af.latest AS low,
                dp.close     * af.adj_factor / latest_af.latest AS close,
                dp.pre_close * af.adj_factor / latest_af.latest AS pre_close,
                dp.pct_chg,
                dp.vol,
                dp.amount,
                af.adj_factor
            FROM daily_price dp
            JOIN adj_factor af
              ON dp.ts_code = af.ts_code AND dp.trade_date = af.trade_date
            JOIN (
                SELECT ts_code, adj_factor AS latest
                FROM adj_factor
                WHERE ts_code = :code
                ORDER BY trade_date DESC LIMIT 1
            ) latest_af ON TRUE
            WHERE dp.ts_code = :code {date_filter}
            ORDER BY dp.trade_date
        """)
    else:
        sql = text(f"""
            SELECT trade_date, open, high, low, close, pre_close, pct_chg, vol, amount
            FROM daily_price
            WHERE ts_code = :code {date_filter}
            ORDER BY trade_date
        """)

    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params=params, index_col="trade_date", parse_dates=["trade_date"])

    return df


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    在 OHLCV DataFrame 上计算常用技术指标。
    输入：get_ohlcv() 返回的 DataFrame
    输出：追加指标列的同一 DataFrame

    包含指标：
      MA(5/10/20/60/120/250)
      EMA(12/26)
      MACD(12,26,9) → macd, macd_signal, macd_hist
      KDJ(9,3,3)    → k, d, j
      RSI(6/14)
      BOLL(20,2)    → boll_upper, boll_mid, boll_lower
      ATR(14)
      OBV
      VWAP（以日线近似：amount*1000 / (vol*100)）
      William%R(14)
      CCI(20)
    """
    # 均线
    for period in (5, 10, 20, 60, 120, 250):
        df[f"ma{period}"] = ta.sma(df["close"], length=period)
    for period in (12, 26):
        df[f"ema{period}"] = ta.ema(df["close"], length=period)

    # MACD
    macd = ta.macd(df["close"], fast=12, slow=26, signal=9)
    if macd is not None and not macd.empty:
        df["macd"]        = macd.iloc[:, 0]  # MACD_12_26_9
        df["macd_signal"] = macd.iloc[:, 1]  # MACDs_12_26_9
        df["macd_hist"]   = macd.iloc[:, 2]  # MACDh_12_26_9

    # KDJ（使用 Stochastic 模拟：K=stoch, D=stoch_signal, J=3*K-2*D）
    stoch = ta.stoch(df["high"], df["low"], df["close"], k=9, d=3, smooth_k=3)
    if stoch is not None and not stoch.empty:
        df["kdj_k"] = stoch.iloc[:, 0]
        df["kdj_d"] = stoch.iloc[:, 1]
        df["kdj_j"] = 3 * df["kdj_k"] - 2 * df["kdj_d"]

    # RSI
    df["rsi6"]  = ta.rsi(df["close"], length=6)
    df["rsi14"] = ta.rsi(df["close"], length=14)

    # BOLL
    bbands = ta.bbands(df["close"], length=20, std=2)
    if bbands is not None and not bbands.empty:
        df["boll_upper"] = bbands.iloc[:, 0]
        df["boll_mid"]   = bbands.iloc[:, 1]
        df["boll_lower"] = bbands.iloc[:, 2]

    # ATR
    df["atr14"] = ta.atr(df["high"], df["low"], df["close"], length=14)

    # OBV
    df["obv"] = ta.obv(df["close"], df["vol"])

    # VWAP（日线近似）
    if "amount" in df.columns and "vol" in df.columns:
        df["vwap"] = (df["amount"] * 1000) / (df["vol"] * 100 + 1e-9)

    # Williams %R
    df["willr14"] = ta.willr(df["high"], df["low"], df["close"], length=14)

    # CCI
    df["cci20"] = ta.cci(df["high"], df["low"], df["close"], length=20)

    return df


def get_indicators(
    ts_code: str,
    start_date: str = None,
    end_date: str = None,
    adjusted: bool = True,
) -> pd.DataFrame:
    """
    一步获取含全套技术指标的 DataFrame。

    示例：
        df = get_indicators("000001.SZ", start_date="20230101")
        print(df[["close", "ma20", "macd", "rsi14"]].tail(20))
    """
    df = get_ohlcv(ts_code, start_date, end_date, adjusted)
    if df.empty:
        return df
    return add_indicators(df)


def get_market_data(trade_date: str) -> pd.DataFrame:
    """
    获取单个交易日全市场截面数据（用于选股/回测）。
    返回：ts_code 为索引，含 close, pct_chg, vol, amount, turnover_rate, total_mv, circ_mv 等
    """
    sql = text("""
        SELECT
            dp.ts_code,
            dp.open, dp.high, dp.low, dp.close,
            dp.pct_chg, dp.vol, dp.amount,
            df.turnover_rate, df.turnover_rate_f, df.volume_ratio,
            df.pe_ttm, df.pb, df.total_mv, df.circ_mv,
            sb.name, sb.industry, sb.market
        FROM daily_price dp
        LEFT JOIN daily_fundamental df
          ON dp.ts_code = df.ts_code AND dp.trade_date = df.trade_date
        LEFT JOIN stock_basic sb
          ON dp.ts_code = sb.ts_code
        WHERE dp.trade_date = :td
    """)
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"td": pd.to_datetime(trade_date, format="%Y%m%d").date()},
                         index_col="ts_code")
    return df
