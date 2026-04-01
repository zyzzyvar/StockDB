#!/usr/bin/env python3
"""
5分钟K线历史回补脚本（Baostock）。

用法：
    python scripts/sync_minute_5min.py --resume           # 单进程断点续传
    python scripts/sync_minute_5min.py --resume --workers 4  # 4进程并行（推荐）
    python scripts/sync_minute_5min.py --start 20240101 --end 20241231
    python scripts/sync_minute_5min.py --codes 600000.SH,000001.SZ

性能说明：
    - 瓶颈在 baostock API（~23s/股），DB写入已优化至 ~2s/股
    - 单进程：5490只 × 25s ≈ 38小时
    - 4进程并行：~10小时；8进程：~5小时
    - 每个进程独立 baostock 会话，互不干扰

后台运行示例：
    nohup python scripts/sync_minute_5min.py --resume --workers 4 \
        > logs/sync_5min.log 2>&1 &
"""
import sys
import argparse
import multiprocessing as mp
from pathlib import Path
from datetime import date, timedelta, datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from stockdb.utils.logger import log
from stockdb.db import engine
from sqlalchemy import text


def get_done_codes(start_date_str: str) -> set:
    """查询 minute_bar_5min 中已有数据的股票代码（用于 --resume 断点续传）"""
    sql = text("""
        SELECT DISTINCT ts_code FROM minute_bar_5min
        WHERE trade_date >= :start
    """)
    start = date.fromisoformat(
        f"{start_date_str[:4]}-{start_date_str[4:6]}-{start_date_str[6:]}"
    )
    with engine.connect() as conn:
        rows = conn.execute(sql, {"start": start}).fetchall()
    return {r[0] for r in rows}


def build_year_ranges(start_date: str, end_date: str) -> list:
    """按年分割日期范围，返回 [(seg_start, seg_end), ...]"""
    start_yr = int(start_date[:4])
    end_yr   = int(end_date[:4])
    ranges = []
    for yr in range(start_yr, end_yr + 1):
        seg_start = max(start_date, f"{yr}0101")
        seg_end   = min(end_date,   f"{yr}1231")
        if seg_start <= seg_end:
            ranges.append((seg_start, seg_end))
    return ranges


def _worker(args):
    """子进程工作函数：处理分配的股票切片"""
    worker_id, ts_codes, start_date, end_date, year_ranges = args

    # 每个子进程独立初始化（SQLAlchemy engine 不跨进程共享）
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from stockdb.fetchers.baostock_fetcher import _ensure_login
    from stockdb.loaders.minute_bar import load_minute_5min_by_code
    from stockdb.utils.logger import log as wlog

    _ensure_login()
    total = 0
    failed = []
    started = datetime.now()

    for i, ts_code in enumerate(ts_codes, 1):
        code_rows = 0
        try:
            for seg_start, seg_end in year_ranges:
                n = load_minute_5min_by_code(ts_code, seg_start, seg_end)
                code_rows += n
            total += code_rows
        except Exception as e:
            wlog.error(f"[W{worker_id}] {ts_code}: {e}")
            failed.append(ts_code)

        if i % 50 == 0:
            elapsed = (datetime.now() - started).total_seconds()
            eta_min = (elapsed / i) * (len(ts_codes) - i) / 60
            wlog.info(
                f"[W{worker_id}] 进度: {i}/{len(ts_codes)} "
                f"({i/len(ts_codes)*100:.1f}%), "
                f"累计 {total:,} 行, 剩余约 {eta_min:.0f} 分钟"
            )

    wlog.info(f"[W{worker_id}] 完成: {total:,} 行, {len(failed)} 失败")
    return total, failed


def main():
    parser = argparse.ArgumentParser(description="5分钟K线历史回补（Baostock）")
    parser.add_argument("--start",   default="20240101",
                        help="起始日期 YYYYMMDD（默认 20240101）")
    parser.add_argument("--end",     default=None,
                        help="结束日期 YYYYMMDD（默认昨日）")
    parser.add_argument("--codes",   default=None,
                        help="指定股票，逗号分隔，如 600000.SH,000001.SZ")
    parser.add_argument("--resume",  action="store_true",
                        help="跳过 minute_bar_5min 中已有数据的股票")
    parser.add_argument("--workers", type=int, default=1,
                        help="并行进程数（默认1，推荐4-8）")
    args = parser.parse_args()

    yesterday  = (date.today() - timedelta(days=1)).strftime("%Y%m%d")
    end_date   = args.end or yesterday
    start_date = args.start

    log.info(f"sync_minute_5min 启动: {start_date} ~ {end_date}, "
             f"workers={args.workers}")

    # 确定股票列表
    if args.codes:
        ts_codes = [c.strip() for c in args.codes.split(",")]
    else:
        from stockdb.loaders.adj_factor import get_all_ts_codes
        ts_codes = get_all_ts_codes()

    log.info(f"目标股票数: {len(ts_codes)}")

    # --resume: 跳过已有数据的股票
    if args.resume:
        done = get_done_codes(start_date)
        ts_codes = [c for c in ts_codes if c not in done]
        log.info(f"--resume: 跳过 {len(done)} 只（已有数据），剩余 {len(ts_codes)} 只")

    if not ts_codes:
        log.info("所有股票已有数据，退出")
        return

    year_ranges = build_year_ranges(start_date, end_date)
    log.info(f"年度分段: {year_ranges}")

    if args.workers == 1:
        # 单进程模式
        from stockdb.fetchers.baostock_fetcher import _ensure_login
        _ensure_login()
        total, failed = _worker((0, ts_codes, start_date, end_date, year_ranges))
    else:
        # 多进程并行模式：将股票列表均分给各 worker
        n = args.workers
        slices = [ts_codes[i::n] for i in range(n)]
        worker_args = [
            (i, slices[i], start_date, end_date, year_ranges)
            for i in range(n)
        ]
        log.info(f"启动 {n} 个并行进程，每进程约 {len(slices[0])} 只股票")

        with mp.Pool(processes=n) as pool:
            results = pool.map(_worker, worker_args)

        total = sum(r[0] for r in results)
        failed = [code for r in results for code in r[1]]

    log.info(f"sync_minute_5min 全部完成: {total:,} 行, {len(failed)} 失败")
    if failed:
        log.warning(f"失败股票（前20）: {failed[:20]}")


if __name__ == "__main__":
    mp.set_start_method("spawn", force=True)  # macOS 安全：避免 fork 时 socket 状态污染
    main()
