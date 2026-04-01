"""
Tushare Pro 数据获取层
所有接口统一返回 pandas DataFrame，列名与数据库字段对齐。
"""
import time
import tushare as ts
import pandas as pd
from stockdb.config import TUSHARE_TOKEN, REQUEST_INTERVAL, TRACKED_INDICES
from stockdb.utils.logger import log
from stockdb.utils.retry import api_retry

# 初始化 Tushare Pro 接口
ts.set_token(TUSHARE_TOKEN)
pro = ts.pro_api()


def _sleep():
    time.sleep(REQUEST_INTERVAL)


# ── 股票基本信息 ─────────────────────────────────────────────

@api_retry()
def fetch_stock_basic(list_status: str = "L") -> pd.DataFrame:
    """获取股票列表（L=上市 D=退市 P=暂停）"""
    df = pro.stock_basic(
        list_status=list_status,
        fields="ts_code,symbol,name,area,industry,market,exchange,"
               "list_date,delist_date,is_hs,list_status",
    )
    _sleep()
    df["list_date"]   = pd.to_datetime(df["list_date"],   format="%Y%m%d", errors="coerce").dt.date
    df["delist_date"] = pd.to_datetime(df["delist_date"], format="%Y%m%d", errors="coerce").dt.date
    return df


# ── 交易日历 ─────────────────────────────────────────────────

@api_retry()
def fetch_trade_calendar(start_date: str, end_date: str, exchange: str = "SSE") -> pd.DataFrame:
    df = pro.trade_cal(
        exchange=exchange,
        start_date=start_date,
        end_date=end_date,
        fields="cal_date,is_open,pretrade_date",
    )
    _sleep()
    df["cal_date"]      = pd.to_datetime(df["cal_date"],      format="%Y%m%d").dt.date
    df["pretrade_date"] = pd.to_datetime(df["pretrade_date"], format="%Y%m%d", errors="coerce").dt.date
    df["exchange"]      = exchange
    return df


# ── 日线行情 ─────────────────────────────────────────────────

@api_retry()
def fetch_daily_price_by_date(trade_date: str) -> pd.DataFrame:
    """按单个交易日获取全市场日线行情"""
    df = pro.daily(
        trade_date=trade_date,
        fields="ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount",
    )
    _sleep()
    if df is None or df.empty:
        return pd.DataFrame()
    df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d").dt.date
    return df


@api_retry()
def fetch_daily_price_by_code(ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """按个股+区间获取日线行情"""
    df = pro.daily(
        ts_code=ts_code,
        start_date=start_date,
        end_date=end_date,
        fields="ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount",
    )
    _sleep()
    if df is None or df.empty:
        return pd.DataFrame()
    df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d").dt.date
    return df


# ── 复权因子 ─────────────────────────────────────────────────

@api_retry()
def fetch_adj_factor(ts_code: str, start_date: str = None, end_date: str = None) -> pd.DataFrame:
    """获取单只股票的复权因子"""
    kwargs = dict(ts_code=ts_code)
    if start_date:
        kwargs["start_date"] = start_date
    if end_date:
        kwargs["end_date"] = end_date
    df = pro.adj_factor(**kwargs, fields="ts_code,trade_date,adj_factor")
    _sleep()
    if df is None or df.empty:
        return pd.DataFrame()
    df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d").dt.date
    return df


@api_retry()
def fetch_adj_factor_by_date(trade_date: str) -> pd.DataFrame:
    """按交易日获取全市场复权因子（一次获取所有股票）"""
    df = pro.adj_factor(trade_date=trade_date, fields="ts_code,trade_date,adj_factor")
    _sleep()
    if df is None or df.empty:
        return pd.DataFrame()
    df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d").dt.date
    return df


# ── 每日基本面 ────────────────────────────────────────────────

@api_retry()
def fetch_daily_basic_by_date(trade_date: str) -> pd.DataFrame:
    """按交易日获取全市场每日基本面指标"""
    df = pro.daily_basic(
        trade_date=trade_date,
        fields="ts_code,trade_date,close,turnover_rate,turnover_rate_f,volume_ratio,"
               "pe,pe_ttm,pb,ps,ps_ttm,dv_ratio,dv_ttm,"
               "total_share,float_share,free_share,total_mv,circ_mv",
    )
    _sleep()
    if df is None or df.empty:
        return pd.DataFrame()
    df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d").dt.date
    return df


@api_retry()
def fetch_daily_basic_by_code(ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """按个股+区间获取每日基本面"""
    df = pro.daily_basic(
        ts_code=ts_code,
        start_date=start_date,
        end_date=end_date,
        fields="ts_code,trade_date,close,turnover_rate,turnover_rate_f,volume_ratio,"
               "pe,pe_ttm,pb,ps,ps_ttm,dv_ratio,dv_ttm,"
               "total_share,float_share,free_share,total_mv,circ_mv",
    )
    _sleep()
    if df is None or df.empty:
        return pd.DataFrame()
    df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d").dt.date
    return df


# ── 指数 ─────────────────────────────────────────────────────

@api_retry()
def fetch_index_basic() -> pd.DataFrame:
    """获取指数基本信息（只获取 TRACKED_INDICES）"""
    rows = []
    for ts_code in TRACKED_INDICES:
        market = "SH" if ts_code.endswith(".SH") else "SZ"
        df = pro.index_basic(ts_code=ts_code, market=market,
                             fields="ts_code,name,market,category,base_date,base_point,list_date,exp_date")
        _sleep()
        if df is not None and not df.empty:
            rows.append(df)
    if not rows:
        return pd.DataFrame()
    result = pd.concat(rows, ignore_index=True)
    for col in ["base_date", "list_date", "exp_date"]:
        result[col] = pd.to_datetime(result[col], format="%Y%m%d", errors="coerce").dt.date
    return result


@api_retry()
def fetch_index_daily(ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """获取指数日线行情"""
    df = pro.index_daily(
        ts_code=ts_code,
        start_date=start_date,
        end_date=end_date,
        fields="ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount",
    )
    _sleep()
    if df is None or df.empty:
        return pd.DataFrame()
    df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d").dt.date
    return df


# ── 龙虎榜 ──────────────────────────────────────────────────

@api_retry()
def fetch_top_list(trade_date: str) -> pd.DataFrame:
    """获取指定交易日的龙虎榜"""
    df = pro.top_list(
        trade_date=trade_date,
        fields="trade_date,ts_code,name,close,pct_change,turnover_rate,amount,"
               "l_buy,l_sell,l_amount,net_amount,net_rate,amount_rate,float_values,reason",
    )
    _sleep()
    if df is None or df.empty:
        return pd.DataFrame()
    df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d").dt.date
    return df


# ── 融资融券 ─────────────────────────────────────────────────

@api_retry()
def fetch_margin_detail(trade_date: str) -> pd.DataFrame:
    """获取指定交易日融资融券明细"""
    df = pro.margin_detail(
        trade_date=trade_date,
        fields="trade_date,ts_code,name,rzye,rqye,rzmre,rqyl,rzche,rqchl,rqjmg,rzrqye,rzrqyecz",
    )
    _sleep()
    if df is None or df.empty:
        return pd.DataFrame()
    df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d").dt.date
    return df


# ── 大宗交易 ─────────────────────────────────────────────────

@api_retry()
def fetch_block_trade(trade_date: str) -> pd.DataFrame:
    """获取指定交易日大宗交易"""
    df = pro.block_trade(
        trade_date=trade_date,
        fields="trade_date,ts_code,price,vol,amount,buyer,seller",
    )
    _sleep()
    if df is None or df.empty:
        return pd.DataFrame()
    df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d").dt.date
    return df


# ── 个股资金流向 ──────────────────────────────────────────────

@api_retry()
def fetch_money_flow(trade_date: str) -> pd.DataFrame:
    """获取指定交易日全市场资金流向（需2000积分）"""
    df = pro.moneyflow(
        trade_date=trade_date,
        fields="ts_code,trade_date,"
               "buy_sm_vol,buy_sm_amount,sell_sm_vol,sell_sm_amount,"
               "buy_md_vol,buy_md_amount,sell_md_vol,sell_md_amount,"
               "buy_lg_vol,buy_lg_amount,sell_lg_vol,sell_lg_amount,"
               "buy_elg_vol,buy_elg_amount,sell_elg_vol,sell_elg_amount,"
               "net_mf_vol,net_mf_amount",
    )
    _sleep()
    if df is None or df.empty:
        return pd.DataFrame()
    df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d").dt.date
    return df


# ── 涨跌停 ───────────────────────────────────────────────────

def fetch_limit_list_range(start_date: str, end_date: str, limit_type: str = "U") -> pd.DataFrame:
    """
    按区间获取涨跌停统计（接口严格限制1次/分钟）。
    不使用通用重试装饰器，改为内部处理：调用前等待65秒，失败则返回空。
    """
    import time
    time.sleep(65)  # 调用前等待，确保与上次调用间隔满足限制
    try:
        df = pro.limit_list_d(
            start_date=start_date,
            end_date=end_date,
            limit_type=limit_type,
            fields="trade_date,ts_code,industry,name,close,pct_chg,amp,"
                   "fc_ratio,fl_ratio,fd_amount,first_time,last_time,"
                   "open_times,strth,limit_amount,ma_amount,duration,limit",
        )
    except Exception as e:
        log.warning(f"limit_list_d {start_date}~{end_date} [{limit_type}] 调用失败: {e}")
        return pd.DataFrame()
    if df is None or df.empty:
        return pd.DataFrame()
    df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d").dt.date
    df = df.rename(columns={"limit": "limit_type"})
    return df
