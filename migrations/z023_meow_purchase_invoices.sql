CREATE TABLE IF NOT EXISTS meow_purchase_invoices (
    id UUID PRIMARY KEY,
    public_code VARCHAR(16) NOT NULL UNIQUE,
    workspace_id BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    package_auf INTEGER NOT NULL CHECK (package_auf > 0),
    package_units BIGINT NOT NULL CHECK (package_units > 0),
    package_price_usd NUMERIC(18, 8) NOT NULL CHECK (package_price_usd > 0),
    billing_currency VARCHAR(8) NOT NULL DEFAULT 'RUB'
        CHECK (billing_currency IN ('RUB', 'USD')),
    locked_exchange_rate NUMERIC(18, 8) NOT NULL CHECK (locked_exchange_rate > 0),
    final_local_amount NUMERIC(18, 2) NOT NULL CHECK (final_local_amount > 0),
    payment_method VARCHAR(32) NOT NULL DEFAULT 'manual',
    external_payment_id VARCHAR(160),
    status VARCHAR(24) NOT NULL DEFAULT 'created'
        CHECK (status IN ('created', 'paid', 'expired', 'cancelled', 'refunded')),
    idempotency_key VARCHAR(160) NOT NULL UNIQUE,
    created_by_user_id BIGINT NOT NULL,
    confirmed_by_user_id BIGINT,
    expires_at TIMESTAMPTZ NOT NULL,
    paid_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (paid_at IS NULL OR status IN ('paid', 'refunded'))
);

CREATE UNIQUE INDEX IF NOT EXISTS meow_purchase_invoices_external_payment_idx
    ON meow_purchase_invoices (external_payment_id)
    WHERE external_payment_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS meow_purchase_invoices_workspace_idx
    ON meow_purchase_invoices (workspace_id, created_at DESC);

CREATE INDEX IF NOT EXISTS meow_purchase_invoices_pending_idx
    ON meow_purchase_invoices (expires_at, created_at)
    WHERE status = 'created';

CREATE TABLE IF NOT EXISTS meow_reconciliation_state (
    singleton_id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (singleton_id = 1),
    last_fingerprint VARCHAR(64),
    last_sent_at TIMESTAMPTZ,
    last_checked_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO meow_reconciliation_state (singleton_id)
VALUES (1)
ON CONFLICT (singleton_id) DO NOTHING;
