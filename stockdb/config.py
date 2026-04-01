"""全局配置"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

# ── 数据库（PostgreSQL）─────────────────────────────────────
DB_HOST     = os.getenv("DB_HOST", "localhost")
DB_PORT     = int(os.getenv("DB_PORT", 5432))
DB_NAME     = os.getenv("DB_NAME", "stockdb")
DB_USER     = os.getenv("DB_USER", "stockdb_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

DATABASE_URL = (
    f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

# ── Tushare ─────────────────────────────────────────────────
TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN", "")

# ── 数据参数 ─────────────────────────────────────────────────
INIT_START_DATE  = os.getenv("INIT_START_DATE", "19901219")
BATCH_DAYS       = int(os.getenv("BATCH_DAYS", 365))
TUSHARE_MAX_ROWS = 4900
REQUEST_INTERVAL = 0.4

# ── Baostock（5分钟K线）────────────────────────────────────────
BAOSTOCK_INTERVAL = 0.05    # 每次 API 调用后等待（秒），约 20 QPS
MINUTE_5MIN_START = "20240101"  # 5分钟K线历史起始日期

# 需要跟踪的核心指数
TRACKED_INDICES = [
    "000001.SH",   # 上证指数
    "399001.SZ",   # 深证成指
    "399006.SZ",   # 创业板指
    "000688.SH",   # 科创50
    "000300.SH",   # 沪深300
    "000905.SH",   # 中证500
    "000852.SH",   # 中证1000
    "000016.SH",   # 上证50
]
