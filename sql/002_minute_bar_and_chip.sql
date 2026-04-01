-- =============================================================
-- 002_minute_bar_and_chip.sql
-- 5分钟K线 + 筹码分布表 DDL + stockscan_user 只读角色
--
-- 执行方法：
--   /Applications/Postgres.app/Contents/Versions/16/bin/psql \
--     -U stockdb_user -d stockdb -f sql/002_minute_bar_and_chip.sql
-- =============================================================


-- =============================================================
-- 1. 5分钟K线（按年分区：2024/2025/2026）
--    规模：~5490只 × 48条/天 × 240天/年 ≈ 6300万行/年
-- =============================================================
CREATE TABLE IF NOT EXISTS minute_bar_5min (
    ts_code     VARCHAR(12)  NOT NULL,
    trade_date  DATE         NOT NULL,
    trade_time  TIME         NOT NULL,
    open        NUMERIC(10,3),
    high        NUMERIC(10,3),
    low         NUMERIC(10,3),
    close       NUMERIC(10,3),
    vol         BIGINT,
    amount      NUMERIC(16,3),
    PRIMARY KEY (ts_code, trade_date, trade_time)
) PARTITION BY RANGE (trade_date);

DO $$
DECLARE yr INT;
BEGIN
    FOR yr IN 2024..2026 LOOP
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS minute_bar_5min_%s
             PARTITION OF minute_bar_5min
             FOR VALUES FROM (%L) TO (%L)',
            yr,
            (yr || '-01-01')::date,
            ((yr + 1) || '-01-01')::date
        );
    END LOOP;
END;
$$;

-- 复合索引（按股票+日期查询）
CREATE INDEX IF NOT EXISTS idx_mb5_code_date ON minute_bar_5min (ts_code, trade_date DESC);
-- BRIN 索引（时序范围扫描优化）
CREATE INDEX IF NOT EXISTS idx_mb5_date_brin ON minute_bar_5min USING BRIN (trade_date);


-- =============================================================
-- 2. 筹码分布（每日快照，非分区，数据量可控）
--    来源：AKShare stock_cyq_em（东方财富）
--    规模：~5490只 × 90天快照 ≈ 490万行（全量）
-- =============================================================
CREATE TABLE IF NOT EXISTS chip_distribution (
    ts_code         VARCHAR(12)  NOT NULL,
    trade_date      DATE         NOT NULL,
    profit_ratio    NUMERIC(8,4),    -- 获利比例（%）
    avg_cost        NUMERIC(10,3),   -- 平均成本（元）
    cost_90_low     NUMERIC(10,3),   -- 90%成本区间下限
    cost_90_high    NUMERIC(10,3),   -- 90%成本区间上限
    concentrate_90  NUMERIC(10,4),   -- 90%集中度
    cost_70_low     NUMERIC(10,3),   -- 70%成本区间下限
    cost_70_high    NUMERIC(10,3),   -- 70%成本区间上限
    concentrate_70  NUMERIC(10,4),   -- 70%集中度
    PRIMARY KEY (ts_code, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_chip_date     ON chip_distribution (trade_date);
CREATE INDEX IF NOT EXISTS idx_chip_code_date ON chip_distribution (ts_code, trade_date DESC);


-- =============================================================
-- 3. 只读用户 stockscan_user（供外部分析应用连接）
--    密码：StockScan_2024#rO（建议部署后修改）
-- =============================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'stockscan_user') THEN
        CREATE ROLE stockscan_user WITH LOGIN PASSWORD 'StockScan_2024#rO';
    END IF;
END;
$$;

GRANT CONNECT ON DATABASE stockdb TO stockscan_user;
GRANT USAGE  ON SCHEMA public    TO stockscan_user;

-- 授权现有所有表的 SELECT
GRANT SELECT ON ALL TABLES IN SCHEMA public TO stockscan_user;

-- 确保未来新建的表也自动继承 SELECT 权限
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT ON TABLES TO stockscan_user;
