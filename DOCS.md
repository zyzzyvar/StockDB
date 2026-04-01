# StockDB 使用文档

> A股量化数据库 · PostgreSQL 16 · 数据截至 2026-03-25

---

## 目录

1. [系统概述](#1-系统概述)
2. [系统架构](#2-系统架构)
3. [数据库设计](#3-数据库设计)
4. [数据逻辑](#4-数据逻辑)
5. [外部应用接入](#5-外部应用接入)
6. [功能支持清单](#6-功能支持清单)
7. [用户与权限](#7-用户与权限)
8. [日常管理](#8-日常管理)
9. [故障处理](#9-故障处理)

---

## 1. 系统概述

StockDB 是一个本地部署的 A 股量化数据基础设施，定位为**数据层**，不内置分析功能。外部分析应用（Python 脚本、Jupyter Notebook、可视化工具、回测框架等）通过标准 PostgreSQL 协议连接并使用数据。

### 当前数据规模

| 数据类型 | 行数 | 时间范围 |
|----------|------|----------|
| 日线行情 | 7,379,581 | 2020-01-02 ~ 2026-03-25 |
| 复权因子 | 7,323,243 | 2020-01-02 ~ 2026-03-25 |
| 每日基本面 | 7,330,588 | 2020-01-02 ~ 2026-03-25 |
| 个股资金流向 | 7,110,334 | 2020-01-02 ~ 2026-03-25 |
| 融资融券 | 4,652,515 | 2020-01-02 ~ 2026-03-24 |
| 龙虎榜 | 95,466 | 2020-01-02 ~ 2026-03-25 |
| 大宗交易 | 202,421 | 2020-01-02 ~ 2026-03-25 |
| 5分钟K线 | 131,364,151 | 2024-01-02 ~ 2026-03-25 |
| 筹码分布 | — | 每日全量更新，近90天 |
| 上市股票数 | 5,491 只 | 含北交所 |
| 指数日线 | 12,056 | 8 个主要指数，5年 |

### 关键参数

```
数据库地址：localhost:5432
数据库名：  stockdb
用户名：    stockdb_user（读写）/ stockscan_user（只读）
密码：      pc3jUs4l3D7c_puPGUuikg（stockdb_user）
数据源：    Tushare Pro（日线主数据源）/ Baostock（5分钟K线）/ AKShare（筹码分布）
自动更新：  每个工作日 15:30（5分钟K线 + 筹码分布）
           每个工作日 18:30（全部日线数据）
```

---

## 2. 系统架构

```
┌─────────────────────────────────────────────┐
│              外部分析应用层                   │
│  Python · Jupyter · Grafana · 自定义回测框架  │
└───────────────────┬─────────────────────────┘
                    │ PostgreSQL 协议 (TCP 5432)
┌───────────────────▼─────────────────────────┐
│         PostgreSQL 16 数据库                 │
│    /Applications/Postgres.app (本机)         │
│    数据目录: ~/Library/Application Support/  │
│             Postgres/var-16/                 │
└───────────────────┬─────────────────────────┘
                    │
┌───────────────────▼─────────────────────────┐
│           StockDB 数据管道                   │
│  ┌─────────────┐    ┌──────────────────────┐ │
│  │  fetchers/  │    │      loaders/        │ │
│  │  tushare_   │───▶│  stock_basic.py      │ │
│  │  fetcher.py │    │  daily_price.py      │ │
│  │             │    │  adj_factor.py       │ │
│  │  baostock_  │    │  daily_fundamental.py│ │
│  │  fetcher.py │    │  money_flow.py       │ │
│  │             │    │  minute_bar.py       │ │
│  │  akshare_   │    │  chip_distribution.py│ │
│  │  fetcher.py │    │  ...                 │ │
│  └─────────────┘    └──────────────────────┘ │
│                                              │
│  ┌─────────────────────────────────────────┐ │
│  │           launchd 定时任务               │ │
│  │   每工作日 15:30 → daily_update_minute.py│ │
│  │   每工作日 18:30 → daily_update.py      │ │
│  └─────────────────────────────────────────┘ │
└─────────────────────────────────────────────┘
                    │                    │
              Tushare Pro API    Baostock / AKShare
              (2100 积分账号)   (5分钟K线 / 筹码)
```

### 项目目录结构

```
StockDB/
├── stockdb/
│   ├── config.py           # 全局配置（DB连接、Token、常量）
│   ├── db.py               # SQLAlchemy 连接池管理
│   ├── indicators.py       # 技术指标计算（供外部应用调用）
│   ├── fetchers/
│   │   ├── tushare_fetcher.py   # 主数据源（所有接口封装）
│   │   ├── baostock_fetcher.py  # Baostock（5分钟K线）
│   │   └── akshare_fetcher.py   # AKShare（筹码分布）
│   └── loaders/
│       ├── base.py              # 通用 UPSERT + bulk_upsert 逻辑
│       ├── stock_basic.py
│       ├── trade_calendar.py
│       ├── daily_price.py
│       ├── adj_factor.py
│       ├── daily_fundamental.py
│       ├── index_data.py
│       ├── top_list.py
│       ├── margin_detail.py
│       ├── block_trade.py
│       ├── money_flow.py
│       ├── limit_list.py
│       ├── minute_bar.py        # 5分钟K线加载
│       └── chip_distribution.py # 筹码分布加载
├── scripts/
│   ├── init_db.py               # 一次性建库建表
│   ├── init_load.py             # 历史全量加载（支持断点续传）
│   ├── daily_update.py          # 每日18:30增量更新（日线数据）
│   ├── daily_update_minute.py   # 每日15:30增量更新（5分钟K线+筹码）
│   ├── sync_minute_5min.py      # 5分钟K线历史回补脚本
│   └── check_data.py            # 数据质量检查
├── sql/
│   ├── 001_create_tables.sql         # 日线表 DDL
│   └── 002_minute_bar_and_chip.sql   # 5分钟K线 + 筹码分布 DDL
├── logs/                        # 运行日志（30天自动清理）
├── .env                         # 敏感配置（Token、密码）
├── com.stockdb.daily-update.plist    # launchd 18:30 任务
├── com.stockdb.minute-update.plist   # launchd 15:30 任务
└── DOCS.md                      # 本文档
```

---

## 3. 数据库设计

### 3.1 表结构总览

```
stockdb (PostgreSQL 16)
  ├── stock_basic              静态基础信息
  ├── trade_calendar           交易日历
  ├── daily_price     [分区]   日线 OHLCV
  ├── adj_factor      [分区]   前复权因子
  ├── daily_fundamental [分区] 每日估值/市值/换手率
  ├── index_basic              指数基本信息
  ├── index_daily              指数日线行情
  ├── top_list                 龙虎榜汇总
  ├── margin_detail            融资融券明细
  ├── block_trade              大宗交易
  ├── money_flow               个股资金流向
  ├── limit_list               涨跌停统计
  ├── minute_bar_5min [分区]   5分钟K线（2024年起）
  ├── chip_distribution        筹码分布（近90天滚动）
  └── data_update_log          更新运维日志
```

`daily_price`、`adj_factor`、`daily_fundamental` 按年分区（1990~2030）；`minute_bar_5min` 按年分区（2024~2026）。所有分区表均在 `trade_date` 上建 BRIN 索引，显著提升时间范围查询性能。

---

### 3.2 各表详细说明

#### `stock_basic` — 股票基本信息

```sql
ts_code       TEXT  PRIMARY KEY   -- Tushare代码，如 '000001.SZ'
symbol        TEXT                -- 纯数字代码，如 '000001'
name          TEXT                -- 股票名称
area          TEXT                -- 所在地域
industry      TEXT                -- 所属行业（申万一级）
market        TEXT                -- 主板/创业板/科创板/北交所
exchange      TEXT                -- SSE/SZSE/BSE
list_date     DATE                -- 上市日期
delist_date   DATE                -- 退市日期（NULL=仍上市）
is_hs         TEXT                -- 沪深港通：H=沪股通 S=深股通 NULL=非标的
list_status   TEXT                -- L=上市中 D=已退市 P=暂停上市
updated_at    TIMESTAMP           -- 最后更新时间
```

**更新频率**：每周一全量刷新，检测新上市与退市变化。

---

#### `trade_calendar` — 交易日历

```sql
cal_date      DATE  PRIMARY KEY   -- 日期
is_open       SMALLINT            -- 1=交易日  0=休市
pretrade_date DATE                -- 上一交易日
exchange      TEXT                -- 默认 SSE（上交所）
```

**用途**：确定哪些日期需要拉取数据；计算任意两日期之间的交易日数。

---

#### `daily_price` — 日线行情 ⭐核心表

```sql
ts_code       TEXT    -- 股票代码
trade_date    DATE    -- 交易日期
open          NUMERIC -- 开盘价（元）
high          NUMERIC -- 最高价
low           NUMERIC -- 最低价
close         NUMERIC -- 收盘价
pre_close     NUMERIC -- 昨收价
change        NUMERIC -- 涨跌额
pct_chg       NUMERIC -- 涨跌幅（%）
vol           NUMERIC -- 成交量（手，1手=100股）
amount        NUMERIC -- 成交额（千元）
PRIMARY KEY (ts_code, trade_date)
```

**注意**：此表存储**原始不复权价格**，复权计算见第4节。

**索引**：
- `(ts_code, trade_date DESC)` — 查询单只股票历史
- `BRIN(trade_date)` — 按日期扫描全市场截面

---

#### `adj_factor` — 复权因子

```sql
ts_code       TEXT    -- 股票代码
trade_date    DATE    -- 交易日期
adj_factor    NUMERIC -- 前复权因子（无量纲）
PRIMARY KEY (ts_code, trade_date)
```

**重要特性**：当股票发生分红、送股、配股时，历史复权因子会**追溯修改**。系统**每个交易日**自动更新当日复权因子（`load_adj_factor_by_date`，一次 API 调用取全市场）；此外建议每周六手动运行 `--repair-adj` 修复近30天追溯变更。

---

#### `daily_fundamental` — 每日基本面指标

```sql
ts_code         TEXT    -- 股票代码
trade_date      DATE    -- 交易日期
close           NUMERIC -- 当日收盘价（用于交叉校验）
turnover_rate   NUMERIC -- 换手率（%，基于总股本）
turnover_rate_f NUMERIC -- 换手率（%，基于自由流通股本）
volume_ratio    NUMERIC -- 量比
pe              NUMERIC -- 市盈率（动态PE）
pe_ttm          NUMERIC -- 市盈率 TTM
pb              NUMERIC -- 市净率
ps              NUMERIC -- 市销率
ps_ttm          NUMERIC -- 市销率 TTM
dv_ratio        NUMERIC -- 股息率（%）
dv_ttm          NUMERIC -- 股息率 TTM（%）
total_share     NUMERIC -- 总股本（万股）
float_share     NUMERIC -- 流通股本（万股）
free_share      NUMERIC -- 自由流通股本（万股）
total_mv        NUMERIC -- 总市值（万元）
circ_mv         NUMERIC -- 流通市值（万元）
PRIMARY KEY (ts_code, trade_date)
```

---

#### `index_basic` — 指数基本信息

当前跟踪的8个指数：

| ts_code | 名称 |
|---------|------|
| 000001.SH | 上证指数 |
| 399001.SZ | 深证成指 |
| 399006.SZ | 创业板指 |
| 000688.SH | 科创50 |
| 000300.SH | 沪深300 |
| 000905.SH | 中证500 |
| 000852.SH | 中证1000 |
| 000016.SH | 上证50 |

如需增加跟踪指数，修改 `stockdb/config.py` 中的 `TRACKED_INDICES` 列表。

---

#### `index_daily` — 指数日线行情

结构与 `daily_price` 相同（OHLCV + 涨跌幅），主键为 `(ts_code, trade_date)`。

---

#### `top_list` — 龙虎榜汇总

```sql
trade_date    DATE    -- 上榜日期
ts_code       TEXT    -- 股票代码
name          TEXT    -- 股票名称
close         NUMERIC -- 收盘价
pct_change    NUMERIC -- 当日涨跌幅（%）
turnover_rate NUMERIC -- 换手率（%）
amount        NUMERIC -- 总成交额（元）
l_buy         NUMERIC -- 龙虎榜买入额（元）
l_sell        NUMERIC -- 龙虎榜卖出额（元）
l_amount      NUMERIC -- 龙虎榜总成交额（元）
net_amount    NUMERIC -- 龙虎榜净买入额（元）
net_rate      NUMERIC -- 净买入额占总成交比（%）
amount_rate   NUMERIC -- 龙虎榜成交额占总成交比（%）
float_values  NUMERIC -- 实际流通市值（元）
reason        TEXT    -- 上榜原因（如"涨幅偏离值达7%"）
PRIMARY KEY (trade_date, ts_code)
```

---

#### `margin_detail` — 融资融券明细

```sql
trade_date DATE   -- 交易日期
ts_code    TEXT   -- 股票代码
rzye       NUMERIC -- 融资余额（元）
rqye       NUMERIC -- 融券余额（元）
rzmre      NUMERIC -- 融资买入额（元）
rqyl       NUMERIC -- 融券余量（股）
rzche      NUMERIC -- 融资偿还额（元）
rqchl      NUMERIC -- 融券偿还量（股）
rqjmg      NUMERIC -- 融券净卖出量（股）
rzrqye     NUMERIC -- 融资融券余额合计（元）
rzrqyecz   NUMERIC -- 融资融券余额差值（元）
```

---

#### `block_trade` — 大宗交易

```sql
id         BIGSERIAL PRIMARY KEY  -- 自增ID（同一天同一股票可多笔）
trade_date DATE    -- 交易日期
ts_code    TEXT    -- 股票代码
price      NUMERIC -- 成交价（元）
vol        NUMERIC -- 成交量（万股）
amount     NUMERIC -- 成交金额（万元）
buyer      TEXT    -- 买方营业部名称
seller     TEXT    -- 卖方营业部名称
```

**注意**：同日同股票可有多笔大宗交易，无唯一约束，更新时采用"先删后插"保证幂等性。

---

#### `money_flow` — 个股资金流向

按单笔成交金额划分散户/中单/大单/超大单的流入流出，是判断主力资金动向的核心数据。

```sql
ts_code        TEXT  -- 股票代码
trade_date     DATE  -- 交易日期
buy_sm_vol     NUMERIC -- 小单买入量（手）  ≤5万元/笔
buy_sm_amount  NUMERIC -- 小单买入金额（万元）
sell_sm_vol    NUMERIC -- 小单卖出量（手）
sell_sm_amount NUMERIC -- 小单卖出金额（万元）
buy_md_vol     NUMERIC -- 中单买入量  5万~20万元/笔
buy_md_amount  NUMERIC
sell_md_vol    NUMERIC
sell_md_amount NUMERIC
buy_lg_vol     NUMERIC -- 大单买入量  20万~100万元/笔
buy_lg_amount  NUMERIC
sell_lg_vol    NUMERIC
sell_lg_amount NUMERIC
buy_elg_vol    NUMERIC -- 超大单买入量  >100万元/笔
buy_elg_amount NUMERIC
sell_elg_vol   NUMERIC
sell_elg_amount NUMERIC
net_mf_vol     NUMERIC -- 净流入量（手）
net_mf_amount  NUMERIC -- 净流入额（万元）
```

---

#### `limit_list` — 涨跌停统计

```sql
trade_date   DATE   -- 日期
ts_code      TEXT   -- 股票代码
limit_type   TEXT   -- U=涨停  D=跌停
industry     TEXT   -- 所属行业
close        NUMERIC -- 收盘价
pct_chg      NUMERIC -- 涨跌幅（%）
amp          NUMERIC -- 振幅（%）
fc_ratio     NUMERIC -- 封单比（封单量/流通股本）
fl_ratio     NUMERIC -- 封单量比（封单量/当日成交量）
fd_amount    NUMERIC -- 封单金额（元）
first_time   TEXT   -- 首次涨/跌停时间（HH:MM:SS）
last_time    TEXT   -- 最后涨/跌停时间
open_times   INT    -- 打开次数（0=一字板）
strth        NUMERIC -- 涨停强度
limit_amount NUMERIC -- 板上成交金额（元）
ma_amount    NUMERIC -- 60日均量（元，衡量承接能力）
duration     INT    -- 涨停持续时长（分钟）
```

**说明**：`limit_list` 接口 Tushare 限制每小时1次调用，历史数据无法批量获取，从系统上线后每日自动积累。

---

#### `minute_bar_5min` — 5分钟K线 ⭐

按年分区（2024/2025/2026），数据来源 Baostock，覆盖全部 A 股（约5500只）。

```sql
ts_code      TEXT    -- 股票代码（如 '000001.SZ'）
trade_date   DATE    -- 交易日期
bar_time     TIME    -- 5分钟区间开始时间（如 09:30:00）
open         NUMERIC -- 开盘价
high         NUMERIC -- 最高价
low          NUMERIC -- 最低价
close        NUMERIC -- 收盘价
vol          BIGINT  -- 成交量（股）
amount       NUMERIC -- 成交额（元）
PRIMARY KEY (ts_code, trade_date, bar_time)
```

**覆盖范围**：2024-01-02 起，每交易日 48 根 K 线（09:30~11:30 / 13:00~15:00）。

**数据规模**：约 1.3 亿行（截至 2026-03-25），约 8 GB（压缩后）。

---

#### `chip_distribution` — 筹码分布

数据来源 AKShare `stock_cyq_em`，每日全量刷新，保留近90天滚动数据。

```sql
ts_code      TEXT    -- 股票代码
trade_date   DATE    -- 交易日期
cost_5pct    NUMERIC -- 5% 获利盘成本价（元）
cost_15pct   NUMERIC -- 15% 获利盘成本价
cost_50pct   NUMERIC -- 50% 获利盘成本价（中位成本）
cost_85pct   NUMERIC -- 85% 获利盘成本价
cost_95pct   NUMERIC -- 95% 获利盘成本价
profit_ratio NUMERIC -- 获利比例（%）
PRIMARY KEY (ts_code, trade_date)
```

**用途**：判断市场平均持仓成本分布、套牢盘压力区、获利盘比例，辅助支撑/压力位分析。

---

#### `data_update_log` — 更新运维日志

记录每次数据更新的结果，是断点续传和数据质量监控的依据。

```sql
id            BIGSERIAL  -- 自增ID
table_name    TEXT       -- 目标表名
update_type   TEXT       -- full=全量  incremental=增量
trade_date    DATE       -- 本次更新对应的交易日
rows_upserted INT        -- 写入行数
status        TEXT       -- success / failed / running
error_msg     TEXT       -- 失败时的错误信息
started_at    TIMESTAMP  -- 开始时间
finished_at   TIMESTAMP  -- 结束时间
```

---

## 4. 数据逻辑

### 4.1 前复权价格计算

数据库存储**原始不复权价格**和**复权因子**，前复权价格在查询时动态计算：

```
前复权价格 = 原始价格 × (该日复权因子 / 最新复权因子)
```

**SQL 示例**：

```sql
-- 查询平安银行前复权收盘价（近30个交易日）
SELECT
    dp.trade_date,
    dp.close                                              AS 原始收盘价,
    dp.close * af.adj_factor / latest.adj_factor          AS 前复权收盘价,
    dp.vol,
    dp.pct_chg
FROM daily_price dp
JOIN adj_factor af
    ON dp.ts_code = af.ts_code AND dp.trade_date = af.trade_date
CROSS JOIN (
    SELECT adj_factor
    FROM adj_factor
    WHERE ts_code = '000001.SZ'
    ORDER BY trade_date DESC
    LIMIT 1
) latest
WHERE dp.ts_code = '000001.SZ'
  AND dp.trade_date >= CURRENT_DATE - INTERVAL '60 days'
ORDER BY dp.trade_date;
```

**Python 示例（推荐方式）**：

```python
from stockdb.indicators import get_ohlcv

# 自动计算前复权，返回 DataFrame
df = get_ohlcv("000001.SZ", start_date="20240101", adjusted=True)
```

---

### 4.2 复权因子的追溯修改

每当股票发生以下事件时，Tushare 会**修改该股历史所有交易日的复权因子**：

- 现金分红（除权）
- 送股/转增（除权）
- 配股（除权）

因此系统每周六 09:00 自动运行修复任务，回刷近 30 天的复权因子：

```bash
python3 scripts/daily_update.py --repair-adj
```

---

### 4.3 全市场截面数据

获取某一交易日所有股票的横截面数据，是选股和回测的基础：

```sql
-- 获取 2026-03-18 全市场截面
SELECT
    dp.ts_code,
    sb.name,
    sb.industry,
    sb.market,
    dp.open, dp.high, dp.low, dp.close,
    dp.pct_chg,
    dp.vol,
    dp.amount,
    df.turnover_rate,
    df.turnover_rate_f,
    df.pe_ttm,
    df.pb,
    df.total_mv   / 10000 AS 总市值_亿元,
    df.circ_mv    / 10000 AS 流通市值_亿元
FROM daily_price dp
JOIN daily_fundamental df
    ON dp.ts_code = df.ts_code AND dp.trade_date = df.trade_date
JOIN stock_basic sb
    ON dp.ts_code = sb.ts_code
WHERE dp.trade_date = '2026-03-18'
ORDER BY df.total_mv DESC;
```

---

### 4.4 资金流向分析逻辑

资金流向按单笔成交金额划分级别：

| 级别 | 单笔金额 | 含义 |
|------|---------|------|
| 小单（sm） | ≤ 5 万元 | 散户 |
| 中单（md） | 5~20 万元 | 中小资金 |
| 大单（lg） | 20~100 万元 | 机构/大户 |
| 超大单（elg） | > 100 万元 | 主力/游资 |

净流入 = 买入 − 卖出。超大单净流入为正且持续，通常表示主力资金介入。

```sql
-- 查询某日超大单净流入 TOP20
SELECT
    mf.ts_code,
    sb.name,
    sb.industry,
    mf.buy_elg_amount - mf.sell_elg_amount  AS 超大单净流入_万元,
    mf.net_mf_amount                          AS 总净流入_万元,
    dp.pct_chg                                AS 涨跌幅
FROM money_flow mf
JOIN stock_basic sb ON mf.ts_code = sb.ts_code
JOIN daily_price dp ON mf.ts_code = dp.ts_code AND mf.trade_date = dp.trade_date
WHERE mf.trade_date = '2026-03-18'
ORDER BY 超大单净流入_万元 DESC
LIMIT 20;
```

---

### 4.5 技术指标计算

技术指标**不预存数据库**，由 `stockdb/indicators.py` 按需计算，避免冗余存储和参数僵化。

**支持的指标**：

| 类型 | 指标 | 参数 |
|------|------|------|
| 均线 | MA | 5/10/20/60/120/250 |
| 指数均线 | EMA | 12/26 |
| 趋势 | MACD | 12/26/9（DIF、DEA、MACD柱） |
| 随机指标 | KDJ | 9/3/3（K、D、J） |
| 强弱指标 | RSI | 6/14 |
| 布林带 | BOLL | 20/2（上轨、中轨、下轨） |
| 真实波幅 | ATR | 14 |
| 能量潮 | OBV | — |
| 成交均价 | VWAP | 日线近似 |
| 威廉指标 | William %R | 14 |
| 顺势指标 | CCI | 20 |

**使用方式**：

```python
from stockdb.indicators import get_indicators, get_ohlcv, get_market_data

# 获取含全套指标的 DataFrame
df = get_indicators("000001.SZ", start_date="20230101")
print(df[["close", "ma20", "macd", "kdj_k", "rsi14", "boll_upper"]].tail(10))

# 只获取 OHLCV（不复权）
df_raw = get_ohlcv("600036.SH", start_date="20200101", adjusted=False)

# 全市场截面（选股、回测）
snapshot = get_market_data("20260318")
low_pb = snapshot[snapshot["pb"] < 1.0].sort_values("circ_mv", ascending=False)
```

---

## 5. 外部应用接入

### 5.1 连接参数

**读写账号**（StockDB 内部管道使用）：

```
Host:     localhost
Port:     5432
Database: stockdb
User:     stockdb_user
Password: pc3jUs4l3D7c_puPGUuikg
```

**只读账号**（外部分析应用推荐使用，如 StockScan）：

```
Host:     localhost
Port:     5432
Database: stockdb
User:     stockscan_user
Password: （见 .env 文件 STOCKSCAN_PASSWORD）
```

`stockscan_user` 对所有当前及未来表拥有 `SELECT` 权限，无写入权限，适合生产分析场景隔离。

### 5.2 Python / SQLAlchemy

```python
from sqlalchemy import create_engine
import pandas as pd

engine = create_engine(
    "postgresql+psycopg2://stockdb_user:pc3jUs4l3D7c_puPGUuikg@localhost:5432/stockdb"
)

# 读取数据
df = pd.read_sql(
    "SELECT * FROM daily_price WHERE ts_code='000001.SZ' ORDER BY trade_date DESC LIMIT 100",
    engine
)
```

### 5.3 使用项目内置工具（推荐）

将 StockDB 目录加入 Python 路径后，可直接使用封装好的函数：

```python
import sys
sys.path.insert(0, "/Users/zyzbot/MyProject/StockDB")

from stockdb.indicators import get_indicators, get_market_data
from stockdb.db import engine
```

### 5.4 DBeaver / TablePlus 等 GUI 工具

新建 PostgreSQL 连接，填入 5.1 的连接参数即可浏览所有表数据。

### 5.5 Jupyter Notebook

```python
# 在 Notebook 中直接使用
import sys
sys.path.insert(0, "/Users/zyzbot/MyProject/StockDB")

import pandas as pd
from stockdb.indicators import get_indicators

df = get_indicators("300750.SZ", start_date="20230101")  # 宁德时代
df[["close", "ma20", "ma60", "rsi14"]].plot(subplots=True, figsize=(14, 8))
```

---

## 6. 功能支持清单

### ✅ 已支持

| 分析场景 | 所需数据表 |
|----------|-----------|
| 个股 K 线技术分析（均线/MACD/KDJ/RSI/BOLL等） | daily_price + adj_factor → indicators.py |
| 全市场估值筛选（PE/PB/市值） | daily_fundamental |
| 资金面分析（换手率/量比） | daily_fundamental |
| 主力资金流向分析 | money_flow |
| 游资/机构动向（龙虎榜） | top_list |
| 融资融券情绪分析 | margin_detail |
| 大宗交易折溢价分析 | block_trade |
| 涨跌停板分析（封单比/打板次数）| limit_list（2026年起积累） |
| 多股对比、板块分析 | stock_basic + daily_price + daily_fundamental |
| 指数走势对比（基准收益） | index_daily |
| 日频历史回测（5年数据） | 全部表 |
| 全市场截面选股 | daily_price + daily_fundamental + stock_basic |
| 5分钟K线技术分析 | minute_bar_5min（2024年起，全市场） |
| 筹码分布 / 获利比例分析 | chip_distribution（近90天滚动） |

### ❌ 未实现（可按需扩展）

| 功能 | 扩展方案 |
|------|---------|
| Tick 级数据 | 存储成本极高，需单独设计 |
| 财务报表（利润表/资产负债表） | Tushare `income()`/`balancesheet()` 接口，季度频率 |
| 十大股东/机构持仓 | Tushare `top10_holders()` 接口，季度频率 |
| 行业/概念板块分类 | Tushare `index_classify()` |
| 分红送股记录 | Tushare `dividend()` |
| 实时行情（盘中） | 需接入实时数据源，超出本系统定位 |

---

## 7. 用户与权限

本数据库实例（`stockdb`）运行在本机，当前共有 4 个角色/用户。

### 7.1 用户总览

| 用户名 | 类型 | 可登录 | 超级用户 | 归属应用 |
|--------|------|--------|----------|----------|
| `zyzbot` | 超级用户 | ✅ | ✅ | macOS 本机系统用户，PostgreSQL 管理员 |
| `stockdb_user` | 普通用户（读写） | ✅ | ❌ | StockDB 数据管道（fetchers / loaders / scripts） |
| `stockscan_user` | 普通用户（只读） | ✅ | ❌ | 外部分析应用（StockScan 等） |
| `stockllm_app` | 普通用户（读写） | ✅ | ❌ | StockLLM — K线图 LLM 分析应用 |

---

### 7.2 各用户权限说明

#### `stockdb_user`

- 拥有 `public` schema 下所有表/序列的完整读写权限
- 通过 `ALTER DEFAULT PRIVILEGES` 自动获得未来新建表的 SELECT 权限授予 `stockscan_user`
- 密码见 `.env` 文件 `DB_PASSWORD`

#### `stockscan_user`

- 仅有 `public` schema 下所有表的 `SELECT` 权限（无写入、无建表）
- 无法访问 `stockllm` schema
- 适合外部分析脚本、Jupyter Notebook、Grafana 等只读场景
- 密码见 `.env` 文件 `STOCKSCAN_PASSWORD`

#### `stockllm_app`

- 拥有独立 `stockllm` schema 及其下所有对象的完整读写权限
- 对 `public` schema 有 `SELECT` 权限（可读取 StockDB 行情数据）
- 密码由 StockLLM 项目独立管理

---

### 7.3 Schema 布局

```
stockdb
  ├── public         ← StockDB 所有业务表（owner: stockdb_user）
  │     ├── daily_price / adj_factor / daily_fundamental ...（日线数据）
  │     ├── minute_bar_5min ...（5分钟K线）
  │     ├── chip_distribution（筹码分布）
  │     └── data_update_log（运维审计）
  │
  └── stockllm       ← StockLLM 应用独立 schema（owner: stockllm_app）
        ├── run_jobs（批次任务记录）
        └── analyses（单股 LLM 分析结果）
```

---

### 7.4 StockLLM Schema 说明

`stockllm` schema 由另一个独立应用 **StockLLM** 维护，与 StockDB 共享同一 PostgreSQL 实例但完全隔离。

**应用功能**：将股票 K 线截图发送给大语言模型（LLM）进行图表分析，将结果持久化存储。

#### `stockllm.run_jobs` — 批次任务记录

```sql
id               BIGSERIAL PRIMARY KEY
batch_name       TEXT NOT NULL        -- 批次名，格式如 '2026-03-24_21-30-00'
batch_path       TEXT NOT NULL        -- 批次数据本地路径
requested_limit  INTEGER              -- 本批次处理上限（NULL=全量）
force_rerun      BOOLEAN DEFAULT false -- 是否强制重跑（忽略缓存）
discovered_count INTEGER              -- 发现的股票数
processed_count  INTEGER              -- 已处理数
succeeded_count  INTEGER              -- 成功数
failed_count     INTEGER              -- 失败数
skipped_count    INTEGER              -- 跳过数（已有缓存）
status           TEXT                 -- running / success / failed
llm_provider     TEXT                 -- LLM 提供商（如 volcengine_ark）
llm_model        TEXT                 -- 模型名（如 doubao-seed-2.0-pro）
llm_endpoint     TEXT                 -- API 端点
prompt_hash      TEXT                 -- 提示词摘要（用于缓存匹配）
started_at       TIMESTAMPTZ
completed_at     TIMESTAMPTZ
```

#### `stockllm.analyses` — 单股分析结果

```sql
id               BIGSERIAL PRIMARY KEY
run_job_id       BIGINT               -- 关联 run_jobs.id
batch_name       TEXT NOT NULL
batch_path       TEXT NOT NULL
stock_code       TEXT NOT NULL        -- 股票代码（如 '002039'）
stock_path       TEXT NOT NULL        -- 该股票数据路径
pdf_path         TEXT                 -- K线图 PDF 路径（可选）
image_count      INTEGER NOT NULL     -- 图片数量
image_files_json JSONB NOT NULL       -- 图片文件列表
prompt_text      TEXT NOT NULL        -- 发送给 LLM 的完整提示词
prompt_hash      TEXT NOT NULL        -- 提示词哈希（缓存 key）
llm_provider     TEXT NOT NULL
llm_model        TEXT NOT NULL
llm_endpoint     TEXT NOT NULL
status           TEXT NOT NULL        -- success / failed
response_text    TEXT                 -- LLM 返回的分析文本
raw_response_json JSONB               -- LLM 原始响应 JSON
error_message    TEXT                 -- 失败时的错误信息
analyzed_at      TIMESTAMPTZ
created_at       TIMESTAMPTZ
updated_at       TIMESTAMPTZ
-- 唯一约束：(batch_name, stock_code, prompt_hash, llm_model)
```

**索引**：
- `idx_analyses_stock_time` — `(stock_code, analyzed_at)` 按股票查历史分析
- `idx_analyses_batch_status_time` — `(batch_name, status, analyzed_at)` 按批次查进度

---

## 8. 日常管理

### 8.1 启动 PostgreSQL（每次重启 Mac 后）

```bash
/Applications/Postgres.app/Contents/Versions/16/bin/pg_ctl \
  -D ~/Library/Application\ Support/Postgres/var-16 \
  -l ~/Library/Logs/PostgreSQL/postgres.log \
  start
```

验证是否在运行：

```bash
/Applications/Postgres.app/Contents/Versions/16/bin/pg_ctl \
  -D ~/Library/Application\ Support/Postgres/var-16 \
  status
```

停止 PostgreSQL：

```bash
/Applications/Postgres.app/Contents/Versions/16/bin/pg_ctl \
  -D ~/Library/Application\ Support/Postgres/var-16 \
  stop
```

---

### 8.2 每日自动更新

系统通过 launchd 注册了两个定时任务，**无需手动操作**：

| 时间 | 脚本 | 内容 | 耗时 |
|------|------|------|------|
| 每工作日 **15:30** | `daily_update_minute.py` | 5分钟K线（Baostock）+ 筹码分布（AKShare） | 约 100 分钟 |
| 每工作日 **18:30** | `daily_update.py` | 日线 OHLCV / 基本面 / 复权因子 / 资金流向 / 龙虎榜 / 融资融券 / 大宗 / 涨跌停 | 约 5 分钟 |

> **18:30 的原因**：龙虎榜（`top_list`）约 18:00 由 Tushare 发布；融资融券（`margin_detail`）为 T+1 数据，系统会在次日自动补录前一交易日数据。

验证定时任务注册状态：

```bash
launchctl list | grep stockdb
```

手动触发今日更新（如需补跑）：

```bash
cd /Users/zyzbot/MyProject/StockDB

# 日线数据
python3 scripts/daily_update.py

# 5分钟K线（跳过筹码，节省90分钟）
python3 scripts/daily_update_minute.py --skip-chip

# 5分钟K线 + 筹码分布（完整流程）
python3 scripts/daily_update_minute.py
```

强制更新指定日期：

```bash
python3 scripts/daily_update.py --date 20260325
python3 scripts/daily_update_minute.py --date 20260325 --skip-chip
```

---

### 8.3 每周维护（建议周六手动运行）

```bash
# 修复近30天复权因子（分红后会追溯修改）
python3 scripts/daily_update.py --repair-adj
```

---

### 8.4 查看数据状态

```bash
python3 scripts/check_data.py
```

输出各表行数、最新数据日期、近期失败记录。

---

### 8.5 查看实时更新日志

```bash
# 跟踪每日更新日志
tail -f logs/stockdb_$(date +%Y-%m-%d).log

# 查看历史日志
ls logs/
```

---

### 8.6 SQL 直连数据库

```bash
/Applications/Postgres.app/Contents/Versions/16/bin/psql \
  -U stockdb_user -d stockdb
```

常用 SQL：

```sql
-- 查看各分区表大小
SELECT
    child.relname      AS 分区表,
    pg_size_pretty(pg_relation_size(child.oid)) AS 大小
FROM pg_inherits
JOIN pg_class parent ON pg_inherits.inhparent = parent.oid
JOIN pg_class child  ON pg_inherits.inhrelid  = child.oid
WHERE parent.relname = 'daily_price'
ORDER BY child.relname;

-- 查看今日更新情况
SELECT table_name, rows_upserted, status, finished_at
FROM data_update_log
WHERE trade_date = CURRENT_DATE
ORDER BY started_at;

-- 查看数据库总大小
SELECT pg_size_pretty(pg_database_size('stockdb'));
```

---

### 8.7 历史数据补充加载

如需补充加载某段历史数据（支持断点续传，已有数据自动跳过）：

```bash
# 补充特定表的特定时段
python3 scripts/init_load.py \
  --start 20190101 \
  --end   20191231 \
  --tables daily_price,adj_factor,daily_fundamental
```

---

## 9. 故障处理

### 9.1 每日更新后数据未更新

**排查步骤**：

```bash
# 1. 查看更新日志
tail -50 logs/stockdb_$(date +%Y-%m-%d).log      # 日线任务
tail -50 logs/launchd_minute_stderr.log           # 5分钟K线任务

# 2. 查看 launchd 输出
cat logs/launchd_stderr.log
cat logs/launchd_minute_stderr.log

# 3. 查看 data_update_log 确认各表状态
psql -U stockdb_user -d stockdb -c \
  "SELECT table_name, trade_date, rows_upserted, status, finished_at
   FROM data_update_log WHERE started_at::date = CURRENT_DATE ORDER BY started_at;"

# 4. 手动触发
python3 scripts/daily_update.py
python3 scripts/daily_update_minute.py --skip-chip

# 5. 检查 PostgreSQL 是否运行
/Applications/Postgres.app/Contents/Versions/16/bin/pg_ctl \
  -D ~/Library/Application\ Support/Postgres/var-16 status
```

---

### 9.2 Mac 重启后数据库连接失败

PostgreSQL 不会随 Mac 启动自动运行（launchd 任务到时间会失败）。手动启动：

```bash
/Applications/Postgres.app/Contents/Versions/16/bin/pg_ctl \
  -D ~/Library/Application\ Support/Postgres/var-16 \
  -l ~/Library/Logs/PostgreSQL/postgres.log start
```

如需开机自启，执行：

```bash
/Applications/Postgres.app/Contents/Versions/16/bin/pg_ctl \
  -D ~/Library/Application\ Support/Postgres/var-16 \
  -l ~/Library/Logs/PostgreSQL/postgres.log \
  -o "-k /tmp" start

# 注册为开机自启服务（需要 launchctl）
# 编辑 Postgres.app 偏好设置中的"自动启动"选项更简便
```

---

### 9.3 某张表数据异常/缺失

```bash
# 重新加载指定表的特定日期范围
python3 scripts/init_load.py \
  --start 20260301 \
  --tables daily_price,daily_fundamental

# 清除异常数据后重新加载（示例：清除 daily_price 某日数据）
psql -U stockdb_user -d stockdb -c \
  "DELETE FROM daily_price WHERE trade_date = '2026-03-18'"
python3 scripts/daily_update.py --date 20260318
```

---

### 9.4 Tushare 接口报错

常见错误及处理：

| 错误信息 | 原因 | 处理 |
|----------|------|------|
| `每分钟最多访问X次` | 调用频率超限 | 等待1分钟后重试 |
| `每小时最多访问X次` | 高频限制接口（如limit_list） | 正常现象，等待自动恢复 |
| `抱歉，您没有访问该接口的权限` | 积分不足 | 检查 tushare.pro 积分余额 |
| `Token无效` | Token 过期或错误 | 更新 `.env` 中的 `TUSHARE_TOKEN` |

检查积分余额：

```python
import tushare as ts
ts.set_token("你的token")
pro = ts.pro_api()
print(pro.query('userbasic', fields='nick_name,account_type,points'))
```

---

### 9.5 磁盘空间不足

```bash
# 查看数据库大小
psql -U stockdb_user -d stockdb -c \
  "SELECT pg_size_pretty(pg_database_size('stockdb'));"

# 清理日志（日志自动30天轮转，也可手动清理）
find /Users/zyzbot/MyProject/StockDB/logs -name "*.gz" -mtime +90 -delete

# 对大表执行 VACUUM 回收空间
psql -U stockdb_user -d stockdb -c "VACUUM ANALYZE daily_price;"
```

---

*文档版本：v2.1 · 2026-03-26*
