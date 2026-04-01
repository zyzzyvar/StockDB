"""涨跌停统计加载（接口限制1次/分钟，按月分段拉取）"""
from datetime import datetime, date
from typing import List
from stockdb.fetchers.tushare_fetcher import fetch_limit_list_range
from stockdb.loaders.base import upsert_dataframe, log_update
from stockdb.utils.logger import log

TABLE = "limit_list"
UPDATE_COLS = [
    "industry", "name", "close", "pct_chg", "amp",
    "fc_ratio", "fl_ratio", "fd_amount", "first_time", "last_time",
    "open_times", "strth", "limit_amount", "ma_amount", "duration",
]


def _month_ranges(start: str, end: str):
    """生成按月分割的 (start, end) 列表"""
    from datetime import timedelta
    import calendar
    s = datetime.strptime(start, "%Y%m%d").date()
    e = datetime.strptime(end, "%Y%m%d").date()
    ranges = []
    cur = s.replace(day=1)
    while cur <= e:
        last_day = calendar.monthrange(cur.year, cur.month)[1]
        month_end = min(cur.replace(day=last_day), e)
        month_start = max(cur, s)
        ranges.append((month_start.strftime("%Y%m%d"), month_end.strftime("%Y%m%d")))
        if cur.month == 12:
            cur = cur.replace(year=cur.year + 1, month=1, day=1)
        else:
            cur = cur.replace(month=cur.month + 1, day=1)
    return ranges


def load_limit_list(start_date: str, end_date: str) -> int:
    """
    按月分段加载涨跌停数据。
    每月U+D共2次调用，每次强制等待61秒（接口限制）。
    5年数据约60个月 × 2次 = 120分钟。
    """
    started = datetime.now()
    total = 0
    months = _month_ranges(start_date, end_date)
    log.info(f"limit_list: 共 {len(months)} 个月段 × 2种类型，预计 {len(months)*2} 分钟")

    for m_start, m_end in months:
        for limit_type in ("U", "D"):
            try:
                df = fetch_limit_list_range(m_start, m_end, limit_type=limit_type)
                if df.empty:
                    log.debug(f"limit_list {m_start}~{m_end} [{limit_type}]: 无数据")
                    continue
                n = upsert_dataframe(df, TABLE,
                                     conflict_cols=["trade_date", "ts_code", "limit_type"],
                                     update_cols=UPDATE_COLS)
                total += n
                log.info(f"limit_list {m_start}~{m_end} [{limit_type}]: upserted {n} rows")
            except Exception as e:
                log.error(f"limit_list {m_start}~{m_end} [{limit_type}]: {e}")

    log.info(f"limit_list 合计 upserted: {total} rows")
    log_update(TABLE, "full", rows_upserted=total, status="success", started_at=started)
    return total


def load_limit_list_by_date(trade_date_str: str) -> int:
    """每日增量更新（单日，仍需等待61秒）"""
    started = datetime.now()
    td = datetime.strptime(trade_date_str, "%Y%m%d").date()
    total = 0
    for limit_type in ("U", "D"):
        try:
            df = fetch_limit_list_range(trade_date_str, trade_date_str, limit_type=limit_type)
            if df.empty:
                continue
            n = upsert_dataframe(df, TABLE,
                                 conflict_cols=["trade_date", "ts_code", "limit_type"],
                                 update_cols=UPDATE_COLS)
            total += n
        except Exception as e:
            log.error(f"limit_list {trade_date_str} [{limit_type}]: {e}")
    log.info(f"limit_list {trade_date_str}: upserted {total} rows")
    log_update(TABLE, "incremental", trade_date=td,
               rows_upserted=total, status="success", started_at=started)
    return total


def load_limit_list_batch(trade_dates: List[str], skip_existing: bool = True) -> int:
    """每日更新调用入口（daily_update.py 用）"""
    if not trade_dates:
        return 0
    return load_limit_list_by_date(trade_dates[-1])  # 增量只取最新一天
