"""大宗交易加载"""
from datetime import datetime
from typing import List
from stockdb.fetchers.tushare_fetcher import fetch_block_trade
from stockdb.loaders.base import upsert_dataframe, log_update, already_updated
from stockdb.utils.logger import log

TABLE = "block_trade"


def load_block_trade_by_date(trade_date_str: str) -> int:
    td = datetime.strptime(trade_date_str, "%Y%m%d").date()
    started = datetime.now()
    try:
        df = fetch_block_trade(trade_date_str)
        if df.empty:
            return 0
        # block_trade 使用 BIGSERIAL id，没有天然唯一键（同一天同一股票可能有多笔）
        # 先删除当日数据再插入，保证幂等性
        from stockdb.db import get_session
        from sqlalchemy import text
        with get_session() as session:
            session.execute(
                text("DELETE FROM block_trade WHERE trade_date = :d"),
                {"d": td}
            )
        # 不需要 upsert，直接 insert
        from stockdb.db import engine
        df.to_sql(TABLE, engine, if_exists="append", index=False, method="multi")
        n = len(df)
        log.info(f"block_trade {trade_date_str}: inserted {n} rows")
        log_update(TABLE, "incremental", trade_date=td,
                   rows_upserted=n, status="success", started_at=started)
        return n
    except Exception as e:
        log.error(f"block_trade {trade_date_str} 加载失败: {e}")
        log_update(TABLE, "incremental", trade_date=td,
                   status="failed", error_msg=str(e), started_at=started)
        raise


def load_block_trade_batch(trade_dates: List[str], skip_existing: bool = True) -> int:
    total = 0
    for td_str in trade_dates:
        td = datetime.strptime(td_str, "%Y%m%d").date()
        if skip_existing and already_updated(TABLE, td):
            continue
        try:
            total += load_block_trade_by_date(td_str)
        except Exception as e:
            log.error(f"block_trade {td_str}: 跳过（{e}）")
    return total
