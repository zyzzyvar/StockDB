"""个股资金流向加载"""
from datetime import datetime
from typing import List
from stockdb.fetchers.tushare_fetcher import fetch_money_flow
from stockdb.loaders.base import upsert_dataframe, log_update, already_updated
from stockdb.utils.logger import log

TABLE = "money_flow"
UPDATE_COLS = [
    "buy_sm_vol", "buy_sm_amount", "sell_sm_vol", "sell_sm_amount",
    "buy_md_vol", "buy_md_amount", "sell_md_vol", "sell_md_amount",
    "buy_lg_vol", "buy_lg_amount", "sell_lg_vol", "sell_lg_amount",
    "buy_elg_vol", "buy_elg_amount", "sell_elg_vol", "sell_elg_amount",
    "net_mf_vol", "net_mf_amount",
]


def load_money_flow_by_date(trade_date_str: str) -> int:
    td = datetime.strptime(trade_date_str, "%Y%m%d").date()
    started = datetime.now()
    try:
        df = fetch_money_flow(trade_date_str)
        if df.empty:
            return 0
        n = upsert_dataframe(df, TABLE,
                             conflict_cols=["ts_code", "trade_date"],
                             update_cols=UPDATE_COLS)
        log.info(f"money_flow {trade_date_str}: upserted {n} rows")
        log_update(TABLE, "incremental", trade_date=td,
                   rows_upserted=n, status="success", started_at=started)
        return n
    except Exception as e:
        log.error(f"money_flow {trade_date_str} 加载失败: {e}")
        log_update(TABLE, "incremental", trade_date=td,
                   status="failed", error_msg=str(e), started_at=started)
        raise


def load_money_flow_batch(trade_dates: List[str], skip_existing: bool = True) -> int:
    total = 0
    for td_str in trade_dates:
        td = datetime.strptime(td_str, "%Y%m%d").date()
        if skip_existing and already_updated(TABLE, td):
            continue
        try:
            total += load_money_flow_by_date(td_str)
        except Exception as e:
            log.error(f"money_flow {td_str}: 跳过（{e}）")
    return total
