CREATE TABLE IF NOT EXISTS kie_exchange_rate_daily (
    check_date DATE PRIMARY KEY,
    source VARCHAR(32) NOT NULL DEFAULT 'nbrb',
    attempted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    effective_date DATE,
    usd_to_byn NUMERIC(18, 8),
    rub_to_byn NUMERIC(18, 8),
    usd_to_rub NUMERIC(18, 8),
    succeeded_at TIMESTAMPTZ,
    error_message TEXT,
    CONSTRAINT kie_exchange_rate_positive_values CHECK (
        (usd_to_byn IS NULL OR usd_to_byn > 0)
        AND (rub_to_byn IS NULL OR rub_to_byn > 0)
        AND (usd_to_rub IS NULL OR usd_to_rub > 0)
    )
);

CREATE INDEX IF NOT EXISTS idx_kie_exchange_rate_success
    ON kie_exchange_rate_daily (effective_date DESC, succeeded_at DESC)
    WHERE succeeded_at IS NOT NULL;
