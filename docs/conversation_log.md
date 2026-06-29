# StockDB 会话日志

---

## Session 1（2026-05-11）

### Q: 近期的自动数据装载正常吗

**用户提问：** 近期的自动数据装载正常吗

**核心结论：**
- launchd 两个任务（daily-update / minute-update）自 2026-04-22 起全部静默失败，累计缺失 10 个交易日数据
- 根因：Homebrew 将 `python3` 符号链接从 3.13 升级到 3.14，而 loguru 等包仅安装在 3.13 下，导致 `ModuleNotFoundError`
- 临时修复：plist 改为 `/usr/local/bin/python3.13`

---

### Q: 未来如何避免Homebrew影响

**用户提问：** 未来如何避免Homebrew影响

**核心结论：**
- 三种方案：venv（推荐）、brew pin、pyenv
- venv 最稳：环境与 Homebrew 符号链接完全隔离，升级后不受影响

---

### Q: 按照方案A来吧 然后自动帮我补录数据

**用户提问：** 按照方案A来吧 然后自动帮我补录数据

**核心结论：**
- 在项目根创建 `.venv`（python3.13），安装全部依赖，两个 plist 改为指向 `.venv/bin/python`
- launchd 重载后恢复正常（退出码 0）
- 补录 2026-04-23 ~ 2026-05-11 共 10 个交易日，全部 9/9 表成功
- `minute_bar_5min` 仍停在 2026-04-02，需另行处理
- L05 经验更新：最终方案为 venv，不再写裸 Python 路径

---

## Session 2（2026-05-22）

### Q: 补录 minute_bar_5min + 筹码分布

**用户提问：** 补吧（K线和连续筹码分布都补）

**核心结论：**
- 发现 launchd minute-update 进程卡死 9 天（筹码分布阶段 hung），kill 后用 nohup 重启脱离会话
- 缺失 30 个交易日（2026-04-08 ~ 2026-05-22），每天约 22 分钟，预计 01:00 完成

---

## Session 3（2026-05-26）

### Q: 为金融市场氛围监控应用建立独立数据库用户

**用户提问：** 我正在构建一个金融市场氛围监控的应用，需要使用数据库，请为该应用建立一个独立的数据库用户，并给出访问指引；同时更新你自己的文档。

**核心结论：**
- 创建用户 `mktmood_app`，只读访问 public schema（SELECT on all tables + DEFAULT PRIVILEGES）
- 创建独立 schema `mktmood` 归该用户所有，供应用写入自己的数据
- 接入方式：host=localhost port=5432 dbname=stockdb user=mktmood_app

---

## Session 4（2026-06-29）

### Q: pg_hba.conf 修复（mktmood_app 远程连接被拒）

**用户提问：** 实际连接验证时遇到数据库侧访问策略问题：192.168.99.150 非 SSL 连接被拒绝，提示当前客户端 10.7.7.66 需要加密；但启用 SSL 后服务端又返回"不支持 SSL 连接"。

**核心结论：**
- 根本原因：pg_hba.conf 中无 mktmood_app 从 10.7.7.66 的 host 规则
- 修复：添加 `host stockdb mktmood_app 10.7.7.66/32 md5`，执行 `pg_reload_conf()`
- 应用代码须使用 `sslmode=disable`（服务端未启用 SSL）

---

## Session 5（2026-06-29）

### Q: 构建美股数据库（日线 + 5分钟K线）

**用户提问：** 基于目前的数据源情况，我们能构建美股的日线、五分钟K线等数据库吗，并做到每日更新？（用户确认：全市场 ~8000只，5分钟新建独立 plist）

**核心结论：**
- 新建4张表：`us_stock_basic`、`us_trade_calendar`、`us_daily_price`（2023~2030分区）、`us_minute_bar_5min`（2026~2030分区）
- 数据源：yfinance（行情）+ NASDAQ Trader 符号文件（股票池）+ pandas_market_calendars（日历）；全部免费无需 API key
- ts_code 格式 `AAPL.US`，yf_symbol 列存 yfinance 原生格式（BRK-B），点转横杠
- trade_time 存储为 ET 墙钟时间（非 UTC），amount 字段为 NULL（yfinance 无此字段）
- 美股日线并入现有 18:30 launchd 任务；美股5分钟新建 plist（北京周二~周六06:00）
- 修复 fetcher 两个 bug：①NASDAQ Trader SSL 证书 → urllib+自定义 SSL 上下文；②yfinance 1.5.1 MultiIndex 列顺序是 (Ticker, Price) → 用 level names 定位而非硬编码 level=1
- 全量回补（12883只 × 2024-01-01起）通过 nohup 在后台运行，预计约2小时
- `stockdb_user` 需显式 `GRANT ALL ON ALL TABLES` 授权（DDL 已更新）
