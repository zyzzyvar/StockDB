"""交易日历加载"""
from datetime import datetime
from stockdb.fetchers.tushare_fetcher import fetch_trade_calendar
from stockdb.loaders.base import upsert_dataframe, log_update
from stockdb.utils.date_utils import today_str
from stockdb.utils.logger import log


def load_trade_calendar(start_date: str = "19901219", end_date: str = None) -> int:
    """加载交易日历（SSE），默认从1990年至今"""
    if end_date is None:
        end_date = today_str()

    started = datetime.now()
    try:
        df = fetch_trade_calendar(start_date, end_date)
        if df.empty:
            return 0
        n = upsert_dataframe(df, "trade_calendar",
                             conflict_cols=["cal_date"],
                             update_cols=["is_open", "pretrade_date"])
        log.info(f"trade_calendar: upserted {n} rows ({start_date}~{end_date})")
        log_update("trade_calendar", "full" if start_date < "20200101" else "incremental",
                   start_date=df["cal_date"].min(), end_date=df["cal_date"].max(),
                   rows_upserted=n, status="success", started_at=started)
        return n
    except Exception as e:
        log.error(f"trade_calendar 加载失败: {e}")
        log_update("trade_calendar", "incremental", status="failed",
                   error_msg=str(e), started_at=started)
        raise
