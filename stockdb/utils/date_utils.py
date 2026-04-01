"""交易日期工具函数"""
from datetime import date, timedelta
from typing import List
import pandas as pd
from sqlalchemy import text
from stockdb.db import engine


def date_to_str(d: date) -> str:
    """date → 'YYYYMMDD' 字符串（Tushare 格式）"""
    return d.strftime("%Y%m%d")


def str_to_date(s: str) -> date:
    """'YYYYMMDD' → date"""
    return date(int(s[:4]), int(s[4:6]), int(s[6:8]))


def get_trade_dates(start: str, end: str) -> List[str]:
    """从数据库查询 [start, end] 区间内的所有交易日，返回 'YYYYMMDD' 列表"""
    sql = text(
        "SELECT to_char(cal_date, 'YYYYMMDD') AS d "
        "FROM trade_calendar "
        "WHERE is_open = 1 "
        "  AND cal_date BETWEEN :start AND :end "
        "ORDER BY cal_date"
    )
    with engine.connect() as conn:
        rows = conn.execute(sql, {"start": start, "end": end}).fetchall()
    return [r[0] for r in rows]


def get_latest_trade_date() -> str:
    """获取数据库中记录的最新交易日（'YYYYMMDD'）"""
    sql = text(
        "SELECT to_char(MAX(cal_date), 'YYYYMMDD') "
        "FROM trade_calendar WHERE is_open = 1"
    )
    with engine.connect() as conn:
        result = conn.execute(sql).scalar()
    return result or date_to_str(date.today())


def split_date_range(start: str, end: str, batch_days: int = 365):
    """将日期区间按 batch_days 切分，返回 (start, end) 列表"""
    s = str_to_date(start)
    e = str_to_date(end)
    ranges = []
    while s <= e:
        batch_end = min(s + timedelta(days=batch_days - 1), e)
        ranges.append((date_to_str(s), date_to_str(batch_end)))
        s = batch_end + timedelta(days=1)
    return ranges


def today_str() -> str:
    return date_to_str(date.today())
