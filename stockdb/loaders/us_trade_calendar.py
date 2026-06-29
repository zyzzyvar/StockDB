"""美股交易日历加载（NYSE，pandas_market_calendars）"""
from datetime import datetime, date
from stockdb.fetchers.us_fetcher import fetch_us_trade_calendar
from stockdb.loaders.base import upsert_dataframe, log_update
from stockdb.utils.logger import log


def load_us_trade_calendar(start_date: str = "20230101", end_date: str = None) -> int:
    """加载/更新 NYSE 交易日历，默认从 2023 年至未来一年"""
    if end_date is None:
        from datetime import timedelta
        end_date = (date.today().replace(year=date.today().year + 1)).strftime("%Y%m%d")

    started = datetime.now()
    try:
        df = fetch_us_trade_calendar(start_date, end_date)
        if df.empty:
            return 0
        n = upsert_dataframe(
            df, "us_trade_calendar",
            conflict_cols=["cal_date"],
            update_cols=["is_open", "pretrade_date", "is_early_close", "market_close_et"],
        )
        log.info(f"us_trade_calendar: upserted {n} rows ({start_date}~{end_date})")
        log_update("us_trade_calendar", "full",
                   start_date=df["cal_date"].min(), end_date=df["cal_date"].max(),
                   rows_upserted=n, status="success", started_at=started)
        return n
    except Exception as e:
        log.error(f"us_trade_calendar 加载失败: {e}")
        log_update("us_trade_calendar", "full", status="failed",
                   error_msg=str(e), started_at=started)
        raise
