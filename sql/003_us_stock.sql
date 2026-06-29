-- ============================================================
-- 美股数据表 DDL
-- 应用方法：psql -d stockdb -f sql/003_us_stock.sql
-- ============================================================

-- 1. 股票/ETF 基本信息
-- ts_code  格式：AAPL.US / BRK-B.US（沿用 600000.SH 后缀惯例）
-- yf_symbol：yfinance 原生格式，NASDAQ 文件 "." 替换为 "-"（如 BRK-B）
CREATE TABLE IF NOT EXISTS us_stock_basic (
    ts_code       VARCHAR(16)  PRIMARY KEY,
    symbol        VARCHAR(12)  NOT NULL,
    yf_symbol     VARCHAR(12)  NOT NULL,
    name          VARCHAR(120),
    exchange      VARCHAR(16),
    security_type VARCHAR(10)  DEFAULT 'CS',
    is_etf        SMALLINT     DEFAULT 0,
    list_status   VARCHAR(2)   DEFAULT 'L',
    updated_at    TIMESTAMP    DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_usb_status   ON us_stock_basic (list_status);
CREATE INDEX IF NOT EXISTS idx_usb_exchange ON us_stock_basic (exchange);

-- 2. 美股交易日历（NYSE，独立表避免改 trade_calendar 主键）
-- market_close_et：实际收盘 ET 墙钟时间（半日市为 13:00，正常为 16:00）
-- is_early_close：半日市（如感恩节次日）标记
CREATE TABLE IF NOT EXISTS us_trade_calendar (
    cal_date        DATE        PRIMARY KEY,
    is_open         SMALLINT    NOT NULL,
    pretrade_date   DATE,
    is_early_close  SMALLINT    DEFAULT 0,
    market_close_et TIME,
    exchange        VARCHAR(10) DEFAULT 'NYSE'
);

-- 3. 美股日线行情（按年分区，覆盖 2023-2030）
-- adj_close：复权价（yfinance 直接提供）
-- amount：NULL，yfinance 无成交额字段
CREATE TABLE IF NOT EXISTS us_daily_price (
    ts_code    VARCHAR(16)   NOT NULL,
    trade_date DATE          NOT NULL,
    open       NUMERIC(16,4),
    high       NUMERIC(16,4),
    low        NUMERIC(16,4),
    close      NUMERIC(16,4),
    adj_close  NUMERIC(16,4),
    pre_close  NUMERIC(16,4),
    change     NUMERIC(16,4),
    pct_chg    NUMERIC(12,4),
    vol        BIGINT,
    amount     NUMERIC(20,4),
    PRIMARY KEY (ts_code, trade_date)
) PARTITION BY RANGE (trade_date);

DO $$
DECLARE yr INT;
BEGIN
    FOR yr IN 2023..2030 LOOP
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS us_daily_price_%s
             PARTITION OF us_daily_price
             FOR VALUES FROM (%L) TO (%L)',
            yr,
            (yr || '-01-01')::date,
            ((yr + 1) || '-01-01')::date
        );
    END LOOP;
END;
$$;

CREATE INDEX IF NOT EXISTS idx_usdp_code_date ON us_daily_price (ts_code, trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_usdp_date_brin ON us_daily_price USING BRIN (trade_date);

-- 4. 美股5分钟K线（按年分区，仅 2026 起，无历史回补）
-- trade_time：ET 墙钟时间（非 UTC），注意：09:30-16:00 ET
-- amount：NULL，yfinance 无成交额
CREATE TABLE IF NOT EXISTS us_minute_bar_5min (
    ts_code    VARCHAR(16) NOT NULL,
    trade_date DATE        NOT NULL,
    trade_time TIME        NOT NULL,
    open       NUMERIC(16,4),
    high       NUMERIC(16,4),
    low        NUMERIC(16,4),
    close      NUMERIC(16,4),
    vol        BIGINT,
    amount     NUMERIC(20,4),
    PRIMARY KEY (ts_code, trade_date, trade_time)
) PARTITION BY RANGE (trade_date);

DO $$
DECLARE yr INT;
BEGIN
    FOR yr IN 2026..2030 LOOP
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS us_minute_bar_5min_%s
             PARTITION OF us_minute_bar_5min
             FOR VALUES FROM (%L) TO (%L)',
            yr,
            (yr || '-01-01')::date,
            ((yr + 1) || '-01-01')::date
        );
    END LOOP;
END;
$$;

CREATE INDEX IF NOT EXISTS idx_usmb5_code_date ON us_minute_bar_5min (ts_code, trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_usmb5_date_brin ON us_minute_bar_5min USING BRIN (trade_date);

-- 5. 授权写权限给数据写入用户（表由 superuser 创建，stockdb_user 需显式授权）
GRANT ALL ON ALL TABLES IN SCHEMA public TO stockdb_user;

-- 6. 授权只读访问给应用用户
GRANT SELECT ON us_stock_basic     TO stockscan_user, mktmood_app;
GRANT SELECT ON us_trade_calendar  TO stockscan_user, mktmood_app;
GRANT SELECT ON us_daily_price     TO stockscan_user, mktmood_app;
GRANT SELECT ON us_minute_bar_5min TO stockscan_user, mktmood_app;
