-- =============================================================
-- StockDB - A股数据库 DDL
-- PostgreSQL 16
-- =============================================================

-- =============================================================
-- 1. 股票基本信息
-- =============================================================
CREATE TABLE IF NOT EXISTS stock_basic (
    ts_code       VARCHAR(12)  PRIMARY KEY,
    symbol        VARCHAR(10)  NOT NULL,
    name          VARCHAR(20)  NOT NULL,
    area          VARCHAR(20),
    industry      VARCHAR(40),
    market        VARCHAR(20),
    exchange      VARCHAR(10),
    list_date     DATE,
    delist_date   DATE,
    is_hs         VARCHAR(2),
    list_status   VARCHAR(2)   DEFAULT 'L',
    updated_at    TIMESTAMP    DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_sb_status   ON stock_basic (list_status);
CREATE INDEX IF NOT EXISTS idx_sb_industry ON stock_basic (industry);


-- =============================================================
-- 2. 交易日历
-- =============================================================
CREATE TABLE IF NOT EXISTS trade_calendar (
    cal_date      DATE         PRIMARY KEY,
    is_open       SMALLINT     NOT NULL,
    pretrade_date DATE,
    exchange      VARCHAR(10)  DEFAULT 'SSE'
);


-- =============================================================
-- 3. 日线行情（按年分区）
-- =============================================================
CREATE TABLE IF NOT EXISTS daily_price (
    ts_code       VARCHAR(12)  NOT NULL,
    trade_date    DATE         NOT NULL,
    open          NUMERIC(12,4),
    high          NUMERIC(12,4),
    low           NUMERIC(12,4),
    close         NUMERIC(12,4),
    pre_close     NUMERIC(12,4),
    change        NUMERIC(12,4),
    pct_chg       NUMERIC(10,4),
    vol           NUMERIC(20,2),
    amount        NUMERIC(20,4),
    PRIMARY KEY (ts_code, trade_date)
) PARTITION BY RANGE (trade_date);

DO $$
DECLARE yr INT;
BEGIN
    FOR yr IN 1990..2030 LOOP
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS daily_price_%s
             PARTITION OF daily_price
             FOR VALUES FROM (%L) TO (%L)',
            yr,
            (yr || '-01-01')::date,
            ((yr + 1) || '-01-01')::date
        );
    END LOOP;
END;
$$;

CREATE INDEX IF NOT EXISTS idx_dp_code_date ON daily_price (ts_code, trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_dp_date_brin ON daily_price USING BRIN (trade_date);


-- =============================================================
-- 4. 复权因子（按年分区）
-- =============================================================
CREATE TABLE IF NOT EXISTS adj_factor (
    ts_code       VARCHAR(12)  NOT NULL,
    trade_date    DATE         NOT NULL,
    adj_factor    NUMERIC(16,6) NOT NULL,
    PRIMARY KEY (ts_code, trade_date)
) PARTITION BY RANGE (trade_date);

DO $$
DECLARE yr INT;
BEGIN
    FOR yr IN 1990..2030 LOOP
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS adj_factor_%s
             PARTITION OF adj_factor
             FOR VALUES FROM (%L) TO (%L)',
            yr,
            (yr || '-01-01')::date,
            ((yr + 1) || '-01-01')::date
        );
    END LOOP;
END;
$$;

CREATE INDEX IF NOT EXISTS idx_af_code_date ON adj_factor (ts_code, trade_date DESC);


-- =============================================================
-- 5. 每日基本面指标（按年分区）
-- =============================================================
CREATE TABLE IF NOT EXISTS daily_fundamental (
    ts_code           VARCHAR(12)  NOT NULL,
    trade_date        DATE         NOT NULL,
    close             NUMERIC(12,4),
    turnover_rate     NUMERIC(12,4),
    turnover_rate_f   NUMERIC(12,4),
    volume_ratio      NUMERIC(12,4),
    pe                NUMERIC(16,4),
    pe_ttm            NUMERIC(16,4),
    pb                NUMERIC(12,4),
    ps                NUMERIC(12,4),
    ps_ttm            NUMERIC(12,4),
    dv_ratio          NUMERIC(12,4),
    dv_ttm            NUMERIC(12,4),
    total_share       NUMERIC(20,4),
    float_share       NUMERIC(20,4),
    free_share        NUMERIC(20,4),
    total_mv          NUMERIC(20,4),
    circ_mv           NUMERIC(20,4),
    PRIMARY KEY (ts_code, trade_date)
) PARTITION BY RANGE (trade_date);

DO $$
DECLARE yr INT;
BEGIN
    FOR yr IN 1990..2030 LOOP
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS daily_fundamental_%s
             PARTITION OF daily_fundamental
             FOR VALUES FROM (%L) TO (%L)',
            yr,
            (yr || '-01-01')::date,
            ((yr + 1) || '-01-01')::date
        );
    END LOOP;
END;
$$;

CREATE INDEX IF NOT EXISTS idx_df_code_date ON daily_fundamental (ts_code, trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_df_date      ON daily_fundamental (trade_date);


-- =============================================================
-- 6. 指数基本信息
-- =============================================================
CREATE TABLE IF NOT EXISTS index_basic (
    ts_code       VARCHAR(12)  PRIMARY KEY,
    name          VARCHAR(60)  NOT NULL,
    market        VARCHAR(10),
    category      VARCHAR(20),
    base_date     DATE,
    base_point    NUMERIC(12,4),
    list_date     DATE,
    exp_date      DATE
);


-- =============================================================
-- 7. 指数日线行情
-- =============================================================
CREATE TABLE IF NOT EXISTS index_daily (
    ts_code       VARCHAR(12)  NOT NULL,
    trade_date    DATE         NOT NULL,
    open          NUMERIC(12,4),
    high          NUMERIC(12,4),
    low           NUMERIC(12,4),
    close         NUMERIC(12,4),
    pre_close     NUMERIC(12,4),
    change        NUMERIC(12,4),
    pct_chg       NUMERIC(10,4),
    vol           NUMERIC(20,2),
    amount        NUMERIC(20,4),
    PRIMARY KEY (ts_code, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_id_date ON index_daily (trade_date);


-- =============================================================
-- 8. 龙虎榜
-- =============================================================
CREATE TABLE IF NOT EXISTS top_list (
    trade_date        DATE         NOT NULL,
    ts_code           VARCHAR(12)  NOT NULL,
    name              VARCHAR(20),
    close             NUMERIC(12,4),
    pct_change        NUMERIC(10,4),
    turnover_rate     NUMERIC(12,4),
    amount            NUMERIC(20,4),
    l_buy             NUMERIC(20,4),
    l_sell            NUMERIC(20,4),
    l_amount          NUMERIC(20,4),
    net_amount        NUMERIC(20,4),
    net_rate          NUMERIC(12,4),
    amount_rate       NUMERIC(12,4),
    float_values      NUMERIC(20,4),
    reason            VARCHAR(200),
    PRIMARY KEY (trade_date, ts_code)
);
CREATE INDEX IF NOT EXISTS idx_tl_date ON top_list (trade_date);


-- =============================================================
-- 9. 融资融券明细
-- =============================================================
CREATE TABLE IF NOT EXISTS margin_detail (
    trade_date    DATE         NOT NULL,
    ts_code       VARCHAR(12)  NOT NULL,
    name          VARCHAR(20),
    rzye          NUMERIC(20,4),
    rqye          NUMERIC(20,4),
    rzmre         NUMERIC(20,4),
    rqyl          NUMERIC(20,4),
    rzche         NUMERIC(20,4),
    rqchl         NUMERIC(20,4),
    rqjmg         NUMERIC(20,4),
    rzrqye        NUMERIC(20,4),
    rzrqyecz      NUMERIC(20,4),
    PRIMARY KEY (trade_date, ts_code)
);
CREATE INDEX IF NOT EXISTS idx_md_date ON margin_detail (trade_date);
CREATE INDEX IF NOT EXISTS idx_md_code ON margin_detail (ts_code, trade_date DESC);


-- =============================================================
-- 10. 大宗交易
-- =============================================================
CREATE TABLE IF NOT EXISTS block_trade (
    id            BIGSERIAL    PRIMARY KEY,
    trade_date    DATE         NOT NULL,
    ts_code       VARCHAR(12)  NOT NULL,
    price         NUMERIC(12,4),
    vol           NUMERIC(20,2),
    amount        NUMERIC(20,4),
    buyer         VARCHAR(100),
    seller        VARCHAR(100)
);
CREATE INDEX IF NOT EXISTS idx_bt_date ON block_trade (trade_date);
CREATE INDEX IF NOT EXISTS idx_bt_code ON block_trade (ts_code, trade_date DESC);


-- =============================================================
-- 11. 个股资金流向
-- =============================================================
CREATE TABLE IF NOT EXISTS money_flow (
    ts_code           VARCHAR(12)  NOT NULL,
    trade_date        DATE         NOT NULL,
    buy_sm_vol        NUMERIC(20,2),
    buy_sm_amount     NUMERIC(20,4),
    sell_sm_vol       NUMERIC(20,2),
    sell_sm_amount    NUMERIC(20,4),
    buy_md_vol        NUMERIC(20,2),
    buy_md_amount     NUMERIC(20,4),
    sell_md_vol       NUMERIC(20,2),
    sell_md_amount    NUMERIC(20,4),
    buy_lg_vol        NUMERIC(20,2),
    buy_lg_amount     NUMERIC(20,4),
    sell_lg_vol       NUMERIC(20,2),
    sell_lg_amount    NUMERIC(20,4),
    buy_elg_vol       NUMERIC(20,2),
    buy_elg_amount    NUMERIC(20,4),
    sell_elg_vol      NUMERIC(20,2),
    sell_elg_amount   NUMERIC(20,4),
    net_mf_vol        NUMERIC(20,2),
    net_mf_amount     NUMERIC(20,4),
    PRIMARY KEY (ts_code, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_mf_date ON money_flow (trade_date);


-- =============================================================
-- 12. 涨跌停统计
-- =============================================================
CREATE TABLE IF NOT EXISTS limit_list (
    trade_date    DATE         NOT NULL,
    ts_code       VARCHAR(12)  NOT NULL,
    industry      VARCHAR(40),
    name          VARCHAR(20),
    close         NUMERIC(12,4),
    pct_chg       NUMERIC(10,4),
    amp           NUMERIC(10,4),
    fc_ratio      NUMERIC(12,4),
    fl_ratio      NUMERIC(12,4),
    fd_amount     NUMERIC(20,4),
    first_time    VARCHAR(10),
    last_time     VARCHAR(10),
    open_times    SMALLINT,
    strth         NUMERIC(12,4),
    limit_amount  NUMERIC(20,4),
    ma_amount     NUMERIC(20,4),
    duration      INTEGER,
    limit_type    VARCHAR(2)   NOT NULL,
    PRIMARY KEY (trade_date, ts_code, limit_type)
);
CREATE INDEX IF NOT EXISTS idx_ll_date      ON limit_list (trade_date);
CREATE INDEX IF NOT EXISTS idx_ll_code_date ON limit_list (ts_code, trade_date DESC);


-- =============================================================
-- 13. 数据更新日志
-- =============================================================
CREATE TABLE IF NOT EXISTS data_update_log (
    id            BIGSERIAL    PRIMARY KEY,
    table_name    VARCHAR(50)  NOT NULL,
    update_type   VARCHAR(20)  NOT NULL,
    trade_date    DATE,
    start_date    DATE,
    end_date      DATE,
    rows_upserted INTEGER      DEFAULT 0,
    status        VARCHAR(10)  NOT NULL,
    error_msg     TEXT,
    started_at    TIMESTAMP    DEFAULT NOW(),
    finished_at   TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_dul_table_date ON data_update_log (table_name, trade_date);
