"""美股交易时段工具：判断最近已收盘的交易日（US Eastern 时区）"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import text
from stockdb.db import engine

ET = ZoneInfo("America/New_York")


def latest_completed_us_session(buffer_min: int = 20) -> date:
    """
    返回最近一个已收盘的美股交易日（NYSE 日历）。

    以 us_trade_calendar.market_close_et 为准，加 buffer_min 分钟缓冲，
    确保不把当天尚未收盘的 session 纳入。

    18:30 北京 ≈ 06:30 ET 当天上午 → 返回的是前一个美股交易日。
    """
    now_et = datetime.now(ET)
    today_et = now_et.date()

    sql = text("""
        SELECT cal_date
        FROM us_trade_calendar
        WHERE is_open = 1
          AND (
              cal_date < :today
              OR (
                  cal_date = :today
                  AND market_close_et IS NOT NULL
                  AND :now_time >= (market_close_et + :buf * INTERVAL '1 minute')
              )
          )
        ORDER BY cal_date DESC
        LIMIT 1
    """)
    with engine.connect() as conn:
        row = conn.execute(sql, {
            "today":    today_et,
            "now_time": now_et.time().replace(tzinfo=None),
            "buf":      buffer_min,
        }).fetchone()
    return row[0] if row else None


def get_us_pending_trade_dates(anchor_table: str, floor_date: str, limit: int = 30) -> list:
    """
    获取 anchor_table 尚未成功/partial 更新的美股交易日列表（升序）。

    anchor_table: 'us_daily_price' 或 'us_minute_bar_5min'
    floor_date:   最早回补日期字符串，如 '20240101'
    limit:        最多返回天数
    """
    max_date = latest_completed_us_session()
    if max_date is None:
        return []

    sql = text("""
        SELECT to_char(tc.cal_date, 'YYYYMMDD')
        FROM us_trade_calendar tc
        WHERE tc.is_open = 1
          AND tc.cal_date >= :floor
          AND tc.cal_date <= :max_date
          AND NOT EXISTS (
              SELECT 1 FROM data_update_log d
              WHERE d.table_name = :anchor
                AND d.trade_date = tc.cal_date
                AND d.status IN ('success', 'partial')
          )
        ORDER BY tc.cal_date DESC
        LIMIT :lim
    """)
    with engine.connect() as conn:
        rows = conn.execute(sql, {
            "floor":    date.fromisoformat(f"{floor_date[:4]}-{floor_date[4:6]}-{floor_date[6:]}"),
            "max_date": max_date,
            "anchor":   anchor_table,
            "lim":      limit,
        }).fetchall()
    return [r[0] for r in reversed(rows)]
