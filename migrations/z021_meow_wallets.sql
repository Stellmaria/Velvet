CREATE TABLE IF NOT EXISTS meow_economy_settings (
    singleton_id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (singleton_id = 1),
    provider_auf_usd NUMERIC(12, 6) NOT NULL DEFAULT 0.020000
        CHECK (provider_auf_usd > 0),
    retail_auf_usd NUMERIC(12, 6) NOT NULL DEFAULT 0.030000
        CHECK (retail_auf_usd >= provider_auf_usd),
    billing_usd_to_rub NUMERIC(12, 4) NOT NULL DEFAULT 79.8500
        CHECK (billing_usd_to_rub > 0),
    updated_by_user_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO meow_economy_settings (singleton_id)
VALUES (1)
ON CONFLICT (singleton_id) DO NOTHING;

CREATE TABLE IF NOT EXISTS meow_wallets (
    workspace_id BIGINT PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,
    available_units BIGINT NOT NULL DEFAULT 0 CHECK (available_units >= 0),
    reserved_units BIGINT NOT NULL DEFAULT 0 CHECK (reserved_units >= 0),
    status VARCHAR(16) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'frozen')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO meow_wallets (workspace_id)
SELECT id
FROM workspaces
ON CONFLICT (workspace_id) DO NOTHING;

CREATE TABLE IF NOT EXISTS meow_wallet_entries (
    id BIGSERIAL PRIMARY KEY,
    workspace_id BIGINT NOT NULL REFERENCES meow_wallets(workspace_id) ON DELETE CASCADE,
    operation_type VARCHAR(24) NOT NULL
        CHECK (
            operation_type IN (
                'grant',
                'purchase',
                'reserve',
                'release',
                'capture',
                'refund',
                'manual_debit',
                'adjustment'
            )
        ),
    amount_units BIGINT NOT NULL CHECK (amount_units <> 0),
    available_after_units BIGINT NOT NULL CHECK (available_after_units >= 0),
    reserved_after_units BIGINT NOT NULL CHECK (reserved_after_units >= 0),
    actor_user_id BIGINT,
    task_id UUID,
    invoice_id UUID,
    idempotency_key VARCHAR(160) NOT NULL UNIQUE,
    comment TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS meow_wallet_entries_workspace_created_idx
    ON meow_wallet_entries (workspace_id, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS meow_wallet_entries_task_idx
    ON meow_wallet_entries (task_id)
    WHERE task_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS meow_wallet_entries_invoice_idx
    ON meow_wallet_entries (invoice_id)
    WHERE invoice_id IS NOT NULL;
