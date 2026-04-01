"""
通用数据加载基础函数：批量 UPSERT 到 PostgreSQL。
所有 loader 模块都调用这里的 upsert_dataframe。
"""
from datetime import date
from typing import List
import pandas as pd
from sqlalchemy import text
from stockdb.db import engine, get_session
from stockdb.utils.logger import log


def upsert_dataframe(
    df: pd.DataFrame,
    table: str,
    conflict_cols: List[str],
    update_cols: List[str] = None,
) -> int:
    """
    将 DataFrame 批量 UPSERT 到 table。

    conflict_cols: 构成唯一约束（主键）的列名列表
    update_cols:   冲突时需要更新的列；None 表示 DO NOTHING
    返回: 写入行数
    """
    if df is None or df.empty:
        return 0

    import numpy as np
    df = df.copy()
    # 将 NaN / NaT 转为 None（PostgreSQL NULL）
    df = df.where(pd.notna(df), None)
    # 再处理 numpy NaN（where 可能漏掉 object 列中的 np.nan）
    df = df.replace({np.nan: None})

    cols = list(df.columns)
    col_list = ", ".join(f'"{c}"' for c in cols)
    placeholder = ", ".join(f":{c}" for c in cols)
    conflict = ", ".join(f'"{c}"' for c in conflict_cols)

    if update_cols:
        updates = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in update_cols)
        upsert_clause = f"ON CONFLICT ({conflict}) DO UPDATE SET {updates}"
    else:
        upsert_clause = f"ON CONFLICT ({conflict}) DO NOTHING"

    sql = text(
        f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholder}) {upsert_clause}'
    )

    records = df.to_dict("records")
    with get_session() as session:
        session.execute(sql, records)

    return len(records)


def bulk_upsert_dataframe(
    df: pd.DataFrame,
    table: str,
    conflict_cols: List[str],
    update_cols: List[str] = None,
    page_size: int = 1000,
) -> int:
    """
    高性能批量 UPSERT：使用 psycopg2.extras.execute_values，
    每批 page_size 行打包成单条 SQL，比逐行 INSERT 快 10-20x。
    适用于大批量写入（如 minute_bar_5min）。
    """
    if df is None or df.empty:
        return 0

    import numpy as np
    from psycopg2.extras import execute_values

    df = df.copy()
    df = df.where(pd.notna(df), None)
    df = df.replace({np.nan: None})

    cols = list(df.columns)
    col_list = ", ".join(f'"{c}"' for c in cols)
    conflict  = ", ".join(f'"{c}"' for c in conflict_cols)

    if update_cols:
        updates = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in update_cols)
        upsert_clause = f"ON CONFLICT ({conflict}) DO UPDATE SET {updates}"
    else:
        upsert_clause = f"ON CONFLICT ({conflict}) DO NOTHING"

    sql = f'INSERT INTO "{table}" ({col_list}) VALUES %s {upsert_clause}'

    # 转为 tuple 列表（execute_values 要求）
    records = [tuple(row[c] for c in cols) for row in df.to_dict("records")]

    raw_conn = engine.raw_connection()
    try:
        with raw_conn.cursor() as cur:
            execute_values(cur, sql, records, page_size=page_size)
        raw_conn.commit()
    except Exception:
        raw_conn.rollback()
        raise
    finally:
        raw_conn.close()

    return len(records)


def log_update(
    table_name: str,
    update_type: str,
    trade_date: date = None,
    start_date: date = None,
    end_date: date = None,
    rows_upserted: int = 0,
    status: str = "success",
    error_msg: str = None,
    started_at=None,
):
    """写入 data_update_log 表"""
    from datetime import datetime
    sql = text(
        "INSERT INTO data_update_log "
        "(table_name, update_type, trade_date, start_date, end_date, "
        " rows_upserted, status, error_msg, started_at, finished_at) "
        "VALUES (:table_name, :update_type, :trade_date, :start_date, :end_date, "
        "        :rows_upserted, :status, :error_msg, :started_at, :finished_at)"
    )
    with get_session() as session:
        session.execute(sql, {
            "table_name":    table_name,
            "update_type":   update_type,
            "trade_date":    trade_date,
            "start_date":    start_date,
            "end_date":      end_date,
            "rows_upserted": rows_upserted,
            "status":        status,
            "error_msg":     error_msg,
            "started_at":    started_at or datetime.now(),
            "finished_at":   datetime.now(),
        })


def already_updated(table_name: str, trade_date: date) -> bool:
    """检查指定表在指定交易日是否已成功更新过"""
    sql = text(
        "SELECT COUNT(*) FROM data_update_log "
        "WHERE table_name = :table AND trade_date = :d AND status = 'success'"
    )
    with engine.connect() as conn:
        count = conn.execute(sql, {"table": table_name, "d": trade_date}).scalar()
    return (count or 0) > 0
