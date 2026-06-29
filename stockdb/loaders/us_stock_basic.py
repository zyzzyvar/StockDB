"""美股股票基本信息加载"""
from datetime import datetime
from stockdb.fetchers.us_fetcher import fetch_us_symbols
from stockdb.loaders.base import upsert_dataframe, log_update
from stockdb.utils.logger import log
from stockdb.db import engine
from sqlalchemy import text

TABLE = "us_stock_basic"


def load_us_stock_basic() -> int:
    """全量刷新美股符号列表（从 NASDAQ Trader 文件）。每周一运行。"""
    started = datetime.now()
    try:
        df = fetch_us_symbols()
        if df.empty:
            log.warning("us_stock_basic: 获取到空符号列表")
            return 0

        current_ts_codes = set(df["ts_code"].tolist())

        n = upsert_dataframe(
            df, TABLE,
            conflict_cols=["ts_code"],
            update_cols=["symbol", "yf_symbol", "name", "exchange",
                         "security_type", "is_etf", "list_status", "updated_at"],
        )
        log.info(f"us_stock_basic: upserted {n} rows")

        # 文件中消失的 symbol 标为退市
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT ts_code FROM us_stock_basic WHERE list_status = 'L'")
            )
            existing = {r[0] for r in result}

        delisted = existing - current_ts_codes
        if delisted:
            with engine.connect() as conn:
                conn.execute(
                    text("UPDATE us_stock_basic SET list_status = 'D' WHERE ts_code = ANY(:codes)"),
                    {"codes": list(delisted)},
                )
                conn.commit()
            log.info(f"us_stock_basic: 标记退市 {len(delisted)} 只")

        log_update(TABLE, "full", rows_upserted=n, status="success", started_at=started)
        return n
    except Exception as e:
        log.error(f"us_stock_basic 加载失败: {e}")
        log_update(TABLE, "full", status="failed", error_msg=str(e), started_at=started)
        raise


def get_us_yf_symbols(active_only: bool = True) -> list:
    """返回 yf_symbol 列表（供 fetcher 使用）"""
    sql = "SELECT yf_symbol FROM us_stock_basic"
    if active_only:
        sql += " WHERE list_status = 'L'"
    sql += " ORDER BY ts_code"
    with engine.connect() as conn:
        rows = conn.execute(text(sql)).fetchall()
    return [r[0] for r in rows]


def get_us_ts_code_map(active_only: bool = True) -> dict:
    """返回 yf_symbol -> ts_code 映射字典"""
    sql = "SELECT yf_symbol, ts_code FROM us_stock_basic"
    if active_only:
        sql += " WHERE list_status = 'L'"
    with engine.connect() as conn:
        rows = conn.execute(text(sql)).fetchall()
    return {r[0]: r[1] for r in rows}
