# StockDB - A股量化数据库

基于 PostgreSQL 的 A 股数据库，支持个股走势持续分析及回测。

## 数据库结构

| 表名 | 说明 | 分区 |
|------|------|------|
| `stock_basic` | 股票基本信息（名称/行业/上市日期等） | — |
| `trade_calendar` | 交易日历 | — |
| `daily_price` | 日线行情（OHLCV、涨跌幅） | 按年分区 |
| `adj_factor` | 前复权因子 | 按年分区 |
| `daily_fundamental` | 每日基本面（PE/PB/市值/换手率）| 按年分区 |
| `index_basic` | 指数基本信息 | — |
| `index_daily` | 指数日线行情 | — |
| `top_list` | 龙虎榜（上榜标的 + 资金统计） | — |
| `margin_detail` | 融资融券明细 | — |
| `block_trade` | 大宗交易 | — |
| `money_flow` | 个股资金流向（超/大/中/小单） | — |
| `limit_list` | 涨跌停统计（封单/打开次数等） | — |
| `data_update_log` | 更新运维日志 | — |

**技术指标不预存**，由下游应用通过 `stockdb.indicators` 按需计算。

---

## 快速开始

### 1. 安装依赖

```bash
# 安装 PostgreSQL
brew install postgresql@16
brew services start postgresql@16

# 安装 Python 依赖
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入数据库密码和 Tushare Token
```

### 3. 初始化数据库（仅首次）

```bash
# 以 postgres 超级用户权限执行
python scripts/init_db.py
```

### 4. 全量历史数据加载

```bash
# 加载全部历史数据（预计 4~10 小时）
python scripts/init_load.py

# 只加载核心表（日线+复权+基本面），更快
python scripts/init_load.py --tables trade_calendar,stock_basic,daily_price,adj_factor,daily_fundamental

# 从指定日期开始（如只要近5年）
python scripts/init_load.py --start 20200101
```

脚本支持**断点续传**：中断后重新运行，已加载的交易日自动跳过。

### 5. 设置每日自动更新

```bash
cp com.stockdb.daily-update.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.stockdb.daily-update.plist
```

每个工作日 **17:30** 自动更新当日数据。

---

## 日常使用

```bash
# 手动触发今日更新
python scripts/daily_update.py

# 更新指定日期
python scripts/daily_update.py --date 20250318

# 修复近30天复权因子（建议每周六运行）
python scripts/daily_update.py --repair-adj

# 查看数据状态
python scripts/check_data.py
```

---

## 在分析应用中使用

```python
from stockdb.indicators import get_indicators, get_ohlcv, get_market_data

# 获取含全套技术指标的日线数据（前复权）
df = get_indicators("000001.SZ", start_date="20230101")
print(df[["close", "ma20", "macd", "rsi14", "boll_upper"]].tail(10))

# 只获取 OHLCV（不复权）
df = get_ohlcv("600036.SH", start_date="20200101", adjusted=False)

# 获取某日全市场截面数据（选股/回测用）
snapshot = get_market_data("20250318")
# 按市净率筛选低估值股票
low_pb = snapshot[snapshot["pb"] < 1.0].sort_values("circ_mv", ascending=False)
```

### 前复权价格计算

```sql
-- 直接 SQL 查询前复权收盘价
SELECT
    dp.trade_date,
    dp.close * af.adj_factor / latest.adj_factor AS adj_close
FROM daily_price dp
JOIN adj_factor af ON dp.ts_code = af.ts_code AND dp.trade_date = af.trade_date
JOIN (SELECT adj_factor FROM adj_factor WHERE ts_code='000001.SZ'
      ORDER BY trade_date DESC LIMIT 1) latest ON TRUE
WHERE dp.ts_code = '000001.SZ'
ORDER BY dp.trade_date;
```

---

## 数据源

| 数据 | 来源 | 所需积分 |
|------|------|---------|
| 日线行情、指数 | Tushare Pro | 基础 |
| 复权因子、基本面 | Tushare Pro | 基础 |
| 资金流向 | Tushare Pro | 2000+ |
| 龙虎榜、融资融券 | Tushare Pro | 600+ |
| 大宗交易 | Tushare Pro | 600+ |
| 指数（备用） | AKShare | 免费 |

---

## 项目结构

```
StockDB/
├── stockdb/
│   ├── config.py           # 全局配置
│   ├── db.py               # 数据库连接
│   ├── indicators.py       # 技术指标计算（供下游应用调用）
│   ├── fetchers/           # 数据获取层（Tushare/AKShare）
│   └── loaders/            # 数据写入层（每表一个模块）
├── scripts/
│   ├── init_db.py          # 数据库初始化
│   ├── init_load.py        # 历史全量加载
│   ├── daily_update.py     # 每日增量更新
│   └── check_data.py       # 数据质量检查
├── sql/
│   └── 001_create_tables.sql  # 建表 DDL（含分区）
└── com.stockdb.daily-update.plist  # macOS 定时任务
```
