#!/usr/bin/env python3
"""
数据质量检查脚本：快速查看数据库状态和近期更新情况。

用法：
    python scripts/check_data.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from stockdb.db import engine


def check():
    queries = {
        "stock_basic (上市中)": "SELECT COUNT(*) FROM stock_basic WHERE list_status='L'",
        "trade_calendar":       "SELECT COUNT(*) FROM trade_calendar WHERE is_open=1",
        "daily_price":          "SELECT COUNT(*) FROM daily_price",
        "adj_factor":           "SELECT COUNT(*) FROM adj_factor",
        "daily_fundamental":    "SELECT COUNT(*) FROM daily_fundamental",
        "index_daily":          "SELECT COUNT(*) FROM index_daily",
        "money_flow":           "SELECT COUNT(*) FROM money_flow",
        "margin_detail":        "SELECT COUNT(*) FROM margin_detail",
        "top_list":             "SELECT COUNT(*) FROM top_list",
        "block_trade":          "SELECT COUNT(*) FROM block_trade",
        "limit_list":           "SELECT COUNT(*) FROM limit_list",
    }

    print("\n── 各表行数 ──────────────────────────────────")
    with engine.connect() as conn:
        for name, sql in queries.items():
            try:
                count = conn.execute(text(sql)).scalar()
                print(f"  {name:<30} {count:>12,}")
            except Exception as e:
                print(f"  {name:<30} ERROR: {e}")

    print("\n── 最新数据日期 ────────────────────────────────")
    date_queries = {
        "daily_price":       "SELECT MAX(trade_date) FROM daily_price",
        "daily_fundamental": "SELECT MAX(trade_date) FROM daily_fundamental",
        "money_flow":        "SELECT MAX(trade_date) FROM money_flow",
        "margin_detail":     "SELECT MAX(trade_date) FROM margin_detail",
        "top_list":          "SELECT MAX(trade_date) FROM top_list",
    }
    with engine.connect() as conn:
        for name, sql in date_queries.items():
            try:
                d = conn.execute(text(sql)).scalar()
                print(f"  {name:<30} {str(d)}")
            except Exception as e:
                print(f"  {name:<30} ERROR: {e}")

    print("\n── 近7天更新日志（失败记录）───────────────────")
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT table_name, trade_date, status, error_msg, finished_at "
            "FROM data_update_log "
            "WHERE status='failed' AND started_at > NOW() - INTERVAL '7 days' "
            "ORDER BY started_at DESC LIMIT 20"
        )).fetchall()
        if rows:
            for r in rows:
                print(f"  [{r[1]}] {r[0]}: {r[4]:%Y-%m-%d %H:%M} - {str(r[3])[:80]}")
        else:
            print("  无失败记录")

    print()


if __name__ == "__main__":
    check()
