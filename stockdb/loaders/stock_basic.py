"""股票基本信息加载"""
from datetime import datetime
from stockdb.fetchers.tushare_fetcher import fetch_stock_basic
from stockdb.loaders.base import upsert_dataframe, log_update
from stockdb.utils.logger import log

UPDATE_COLS = [
    "symbol", "name", "area", "industry", "market", "exchange",
    "list_date", "delist_date", "is_hs", "list_status", "updated_at",
]


def load_stock_basic() -> int:
    """全量刷新股票基本信息（含上市、退市、暂停上市）"""
    started = datetime.now()
    total = 0
    try:
        for status in ("L", "D", "P"):
            df = fetch_stock_basic(list_status=status)
            if df.empty:
                continue
            df["updated_at"] = datetime.now()
            n = upsert_dataframe(df, "stock_basic",
                                 conflict_cols=["ts_code"],
                                 update_cols=UPDATE_COLS)
            log.info(f"stock_basic [{status}]: upserted {n} rows")
            total += n

        log_update("stock_basic", "full",
                   rows_upserted=total, status="success", started_at=started)
    except Exception as e:
        log.error(f"stock_basic 加载失败: {e}")
        log_update("stock_basic", "full", status="failed",
                   error_msg=str(e), started_at=started)
        raise
    return total
