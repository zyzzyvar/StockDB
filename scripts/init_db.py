#!/usr/bin/env python3
"""
初始化数据库：创建表结构（PostgreSQL via Postgres.app）
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
from stockdb.config import DATABASE_URL

SQL_FILE = Path(__file__).parent.parent / "sql" / "001_create_tables.sql"


def main():
    print("=" * 60)
    print("StockDB 数据库初始化")
    print(f"连接: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else DATABASE_URL}")
    print("=" * 60)

    engine = create_engine(DATABASE_URL, isolation_level="AUTOCOMMIT")

    # 等待连接
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("✓ 数据库连接成功")
    except Exception as e:
        print(f"✗ 连接失败: {e}")
        sys.exit(1)

    # 执行 DDL
    print("\n执行建表 DDL ...")
    sql = SQL_FILE.read_text(encoding="utf-8")
    with engine.connect() as conn:
        conn.execute(text(sql))
    print("✓ DDL 执行完成")

    # 给用户授权
    with engine.connect() as conn:
        conn.execute(text("GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO stockdb_user"))
        conn.execute(text("GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO stockdb_user"))
    print("✓ 权限授予完成")

    # 验证
    expected = [
        "stock_basic", "trade_calendar", "daily_price", "adj_factor",
        "daily_fundamental", "index_basic", "index_daily",
        "top_list", "margin_detail", "block_trade", "money_flow",
        "limit_list", "data_update_log",
    ]
    print("\n验证表结构 ...")
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
        )).fetchall()
    existing = {r[0] for r in rows}
    all_ok = True
    for t in expected:
        ok = t in existing
        print(f"  {'✓' if ok else '✗'}  {t}")
        if not ok:
            all_ok = False

    print(f"\n{'✓ 初始化成功！' if all_ok else '✗ 部分表缺失'}")
    if all_ok:
        print("  下一步: python scripts/init_load.py")


if __name__ == "__main__":
    main()
