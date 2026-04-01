"""
筹码分布数据加载（AKShare stock_cyq_em，东方财富源）

每只股票一次调用返回最近约90个交易日的每日快照。
AKShare 使用 lazy import 避免 macOS SSL 问题。
"""
import time
from datetime import datetime
from typing import List
import pandas as pd

from stockdb.loaders.base import upsert_dataframe, log_update
from stockdb.utils.logger import log

TABLE         = "chip_distribution"
CONFLICT_COLS = ["ts_code", "trade_date"]
UPDATE_COLS   = [
    "profit_ratio", "avg_cost",
    "cost_90_low", "cost_90_high", "concentrate_90",
    "cost_70_low",  "cost_70_high",  "concentrate_70",
]

# AKShare 返回的中文列名 → 数据库字段名
COLUMN_MAP = {
    "日期":      "trade_date",
    "获利比例":  "profit_ratio",
    "平均成本":  "avg_cost",
    "90成本-低": "cost_90_low",
    "90成本-高": "cost_90_high",
    "90集中度":  "concentrate_90",
    "70成本-低": "cost_70_low",
    "70成本-高": "cost_70_high",
    "70集中度":  "concentrate_70",
}


def _fetch_chip(symbol: str) -> pd.DataFrame:
    """AKShare lazy import，返回最近~90天快照"""
    try:
        import akshare as ak
    except ImportError:
        log.error("akshare 未安装，无法获取筹码分布")
        return pd.DataFrame()

    time.sleep(1.0)  # 约 1 req/sec，避免被东方财富封 IP
    try:
        df = ak.stock_cyq_em(symbol=symbol, adjust="")
    except Exception as e:
        log.warning(f"chip_distribution {symbol}: AKShare 调用失败: {e}")
        return pd.DataFrame()

    return df if (df is not None and not df.empty) else pd.DataFrame()


def load_chip_for_code(ts_code: str) -> int:
    """加载单只股票的筹码分布（最近约90个交易日）"""
    symbol = ts_code.split(".")[0]  # '600000.SH' → '600000'
    df = _fetch_chip(symbol)
    if df.empty:
        return 0

    df = df.rename(columns=COLUMN_MAP)
    df["ts_code"] = ts_code
    df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce").dt.date
    df = df.dropna(subset=["trade_date"])

    for col in UPDATE_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    keep = ["ts_code", "trade_date"] + [c for c in UPDATE_COLS if c in df.columns]
    df = df[keep]

    return upsert_dataframe(df, TABLE, CONFLICT_COLS, UPDATE_COLS)


def load_chip_daily() -> int:
    """
    全市场筹码分布全量更新（约5490只，约90分钟）。
    写入 data_update_log。
    """
    from stockdb.loaders.adj_factor import get_all_ts_codes
    started = datetime.now()
    ts_codes = get_all_ts_codes()
    total = 0
    failed = 0

    for i, ts_code in enumerate(ts_codes, 1):
        try:
            n = load_chip_for_code(ts_code)
            total += n
        except Exception as e:
            log.warning(f"chip_distribution {ts_code}: {e}")
            failed += 1

        if i % 100 == 0:
            elapsed = (datetime.now() - started).total_seconds()
            eta_min = (elapsed / i) * (len(ts_codes) - i) / 60
            log.info(f"chip_distribution 进度: {i}/{len(ts_codes)}, "
                     f"累计 {total} 行, 剩余约 {eta_min:.0f} 分钟")

    status = "success" if failed == 0 else "partial"
    log.info(f"chip_distribution 全量完成: {total} 行, {failed} 失败")
    log_update(TABLE, "full", rows_upserted=total, status=status,
               started_at=started,
               error_msg=f"{failed} stocks failed" if failed else None)
    return total
