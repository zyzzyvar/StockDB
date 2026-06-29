#!/usr/bin/env python3
"""
美股历史数据全量初始化（日线两年回补）。

加载顺序：us_trade_calendar → us_stock_basic → us_daily_price

用法：
    # 先小样本验证
    python scripts/init_load_us.py --limit 20 --start 20240101 --end 20240131

    # 全量回补（约 100 yfinance 批次，建议非美股交易时段运行）
    python scripts/init_load_us.py

    # 指定时间范围
    python scripts/init_load_us.py --start 20240101 --end 20260526

    # 调整批次大小（降低限速风险）
    python scripts/init_load_us.py --chunk-size 50

注意：
  - us_daily_price 按符号批量拉取（非逐日），大幅减少 API 调用次数
  - upsert 幂等，可安全重跑
  - 建议美股非交易时段（北京时间上午）运行，避免触发 IP 软封
  - 5分钟K线无历史回补（yfinance 仅支持近60天intraday），从当日起由 launchd 定时收录
"""
import sys
import argparse
from pathlib import Path
from datetime import date, datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from stockdb.utils.logger import log
from stockdb.config import US_DAILY_START, US_YF_CHUNK_SIZE


def load_calendar(start: str, end: str):
    log.info(f"[1/3] 加载美股交易日历 ({start}~{end})")
    from stockdb.loaders.us_trade_calendar import load_us_trade_calendar
    n = load_us_trade_calendar(start, end)
    log.info(f"us_trade_calendar: {n} rows")


def load_symbols():
    log.info("[2/3] 加载美股股票池（NASDAQ Trader）")
    from stockdb.loaders.us_stock_basic import load_us_stock_basic
    n = load_us_stock_basic()
    log.info(f"us_stock_basic: {n} rows")


def load_daily_prices(start: str, end: str, limit: int = None, chunk_size: int = None):
    from stockdb.loaders.us_stock_basic import get_us_yf_symbols
    from stockdb.loaders.us_daily_price import load_us_daily_by_codes

    cs = chunk_size or US_YF_CHUNK_SIZE
    yf_symbols = get_us_yf_symbols()

    if limit:
        yf_symbols = yf_symbols[:limit]
        log.info(f"[3/3] 美股日线回补（限 {limit} 只，{start}~{end}）")
    else:
        log.info(f"[3/3] 美股日线回补（{len(yf_symbols)} 只，{start}~{end}，chunk={cs}）")

    chunks = [yf_symbols[i:i + cs] for i in range(0, len(yf_symbols), cs)]
    total = 0
    for i, chunk in enumerate(chunks):
        try:
            n = load_us_daily_by_codes(chunk, start, end)
            total += n
            log.info(f"  chunk {i+1}/{len(chunks)}: {n} rows（已累计 {total}）")
        except Exception as e:
            log.error(f"  chunk {i+1}/{len(chunks)} 失败: {e}，继续")

    log.info(f"us_daily_price 回补完成: 共 {total} rows")
    return total


def main():
    parser = argparse.ArgumentParser(description="美股历史数据全量初始化")
    parser.add_argument("--start",      default=US_DAILY_START, help="起始日期 YYYYMMDD（默认两年前）")
    parser.add_argument("--end",        default=date.today().strftime("%Y%m%d"), help="截止日期 YYYYMMDD")
    parser.add_argument("--limit",      type=int, default=None, help="限制符号数量（用于 dry-run）")
    parser.add_argument("--chunk-size", type=int, default=None, help="每批 yfinance 下载的 ticker 数")
    parser.add_argument("--skip-calendar",  action="store_true", help="跳过交易日历加载")
    parser.add_argument("--skip-symbols",   action="store_true", help="跳过股票池加载")
    parser.add_argument("--skip-daily",     action="store_true", help="跳过日线回补")
    args = parser.parse_args()

    log.info(f"init_load_us 启动: {datetime.now():%Y-%m-%d %H:%M:%S}")
    log.info(f"  范围: {args.start} ~ {args.end}  limit={args.limit}  chunk={args.chunk_size}")

    if not args.skip_calendar:
        load_calendar(args.start, args.end)

    if not args.skip_symbols:
        load_symbols()

    if not args.skip_daily:
        load_daily_prices(args.start, args.end, args.limit, args.chunk_size)

    log.info(f"init_load_us 完成: {datetime.now():%Y-%m-%d %H:%M:%S}")


if __name__ == "__main__":
    main()
