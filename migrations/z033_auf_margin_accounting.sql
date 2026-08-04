-- Build an auditable generation-economics ledger.
-- New purchases keep their actual USD revenue basis, wallet units are allocated
-- FIFO to generation charges, and successful tasks receive an immutable P&L row.

ALTER TABLE auf_economy_settings
    ADD COLUMN IF NOT EXISTS pricing_strategy VARCHAR(24) NOT NULL DEFAULT 'target_margin';
ALTER TABLE auf_economy_settings
    ADD COLUMN IF NOT EXISTS target_margin_percent NUMERIC(8, 4) NOT NULL DEFAULT 30.0000;
ALTER TABLE auf_economy_settings
    ADD COLUMN IF NOT EXISTS minimum_contribution_margin_percent NUMERIC(8, 4) NOT NULL DEFAULT 10.0000;
ALTER TABLE auf_economy_settings
    ADD COLUMN IF NOT EXISTS allow_subsidized_generations BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE auf_economy_settings
    ADD COLUMN IF NOT EXISTS dynamic_reserve_enabled BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE auf_economy_settings
    ADD COLUMN IF NOT EXISTS dynamic_reserve_cap_percent NUMERIC(8, 4) NOT NULL DEFAULT 25.0000;

ALTER TABLE auf_economy_settings
    DROP CONSTRAINT IF EXISTS auf_economy_settings_pricing_strategy_check;
ALTER TABLE auf_economy_settings
    ADD CONSTRAINT auf_economy_settings_pricing_strategy_check
    CHECK (pricing_strategy IN ('markup', 'target_margin'));
ALTER TABLE auf_economy_settings
    DROP CONSTRAINT IF EXISTS auf_economy_settings_target_margin_percent_check;
ALTER TABLE auf_economy_settings
    ADD CONSTRAINT auf_economy_settings_target_margin_percent_check
    CHECK (target_margin_percent >= 0 AND target_margin_percent < 100);
ALTER TABLE auf_economy_settings
    DROP CONSTRAINT IF EXISTS auf_economy_settings_minimum_contribution_margin_check;
ALTER TABLE auf_economy_settings
    ADD CONSTRAINT auf_economy_settings_minimum_contribution_margin_check
    CHECK (
        minimum_contribution_margin_percent >= 0
        AND minimum_contribution_margin_percent < 100
    );
ALTER TABLE auf_economy_settings
    DROP CONSTRAINT IF EXISTS auf_economy_settings_dynamic_reserve_cap_check;
ALTER TABLE auf_economy_settings
    ADD CONSTRAINT auf_economy_settings_dynamic_reserve_cap_check
    CHECK (dynamic_reserve_cap_percent >= 0 AND dynamic_reserve_cap_percent <= 1000);

-- 42.86 percent markup is approximately a 30 percent gross margin. Switching the
-- default strategy therefore preserves the approved nominal economics while
-- expressing the business rule directly.
UPDATE auf_economy_settings
SET pricing_strategy = 'target_margin',
    target_margin_percent = 30.0000,
    minimum_contribution_margin_percent = 10.0000,
    allow_subsidized_generations = FALSE,
    dynamic_reserve_enabled = TRUE,
    dynamic_reserve_cap_percent = 25.0000,
    updated_at = NOW()
WHERE singleton_id = 1;

ALTER TABLE auf_task_charges
    ADD COLUMN IF NOT EXISTS pricing_strategy VARCHAR(24) NOT NULL DEFAULT 'markup';
ALTER TABLE auf_task_charges
    ADD COLUMN IF NOT EXISTS target_margin_percent NUMERIC(8, 4);
ALTER TABLE auf_task_charges
    ADD COLUMN IF NOT EXISTS operational_reserve_percent NUMERIC(8, 4) NOT NULL DEFAULT 0;
ALTER TABLE auf_task_charges
    ADD COLUMN IF NOT EXISTS operational_reserve_usd NUMERIC(18, 8) NOT NULL DEFAULT 0;
ALTER TABLE auf_task_charges
    ADD COLUMN IF NOT EXISTS minimum_revenue_usd NUMERIC(18, 8) NOT NULL DEFAULT 0;
ALTER TABLE auf_task_charges
    ADD COLUMN IF NOT EXISTS actual_provider_cost_usd NUMERIC(18, 8);
ALTER TABLE auf_task_charges
    ADD COLUMN IF NOT EXISTS subsidy_guard_applied BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE auf_task_charges
    DROP CONSTRAINT IF EXISTS auf_task_charges_pricing_strategy_check;
ALTER TABLE auf_task_charges
    ADD CONSTRAINT auf_task_charges_pricing_strategy_check
    CHECK (pricing_strategy IN ('markup', 'target_margin', 'user_markup'));
ALTER TABLE auf_task_charges
    DROP CONSTRAINT IF EXISTS auf_task_charges_target_margin_percent_check;
ALTER TABLE auf_task_charges
    ADD CONSTRAINT auf_task_charges_target_margin_percent_check
    CHECK (
        target_margin_percent IS NULL
        OR (target_margin_percent >= 0 AND target_margin_percent < 100)
    );
ALTER TABLE auf_task_charges
    DROP CONSTRAINT IF EXISTS auf_task_charges_operational_reserve_percent_check;
ALTER TABLE auf_task_charges
    ADD CONSTRAINT auf_task_charges_operational_reserve_percent_check
    CHECK (operational_reserve_percent >= 0 AND operational_reserve_percent <= 1000);
ALTER TABLE auf_task_charges
    DROP CONSTRAINT IF EXISTS auf_task_charges_operational_reserve_usd_check;
ALTER TABLE auf_task_charges
    ADD CONSTRAINT auf_task_charges_operational_reserve_usd_check
    CHECK (operational_reserve_usd >= 0);
ALTER TABLE auf_task_charges
    DROP CONSTRAINT IF EXISTS auf_task_charges_minimum_revenue_usd_check;
ALTER TABLE auf_task_charges
    ADD CONSTRAINT auf_task_charges_minimum_revenue_usd_check
    CHECK (minimum_revenue_usd >= 0);
ALTER TABLE auf_task_charges
    DROP CONSTRAINT IF EXISTS auf_task_charges_actual_provider_cost_usd_check;
ALTER TABLE auf_task_charges
    ADD CONSTRAINT auf_task_charges_actual_provider_cost_usd_check
    CHECK (actual_provider_cost_usd IS NULL OR actual_provider_cost_usd > 0);

CREATE TABLE IF NOT EXISTS auf_revenue_lots (
    id BIGSERIAL PRIMARY KEY,
    workspace_id BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    source_entry_id BIGINT UNIQUE,
    source_invoice_id UUID,
    source_type VARCHAR(24) NOT NULL
        CHECK (source_type IN ('purchase', 'grant', 'adjustment', 'legacy_estimate')),
    basis_quality VARCHAR(16) NOT NULL
        CHECK (basis_quality IN ('actual', 'estimated', 'zero')),
    original_units BIGINT NOT NULL CHECK (original_units > 0),
    remaining_units BIGINT NOT NULL CHECK (remaining_units >= 0),
    gross_revenue_usd NUMERIC(20, 8) NOT NULL CHECK (gross_revenue_usd >= 0),
    remaining_revenue_usd NUMERIC(20, 8) NOT NULL CHECK (remaining_revenue_usd >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (remaining_units <= original_units),
    CHECK (remaining_revenue_usd <= gross_revenue_usd + 0.00000001)
);

CREATE INDEX IF NOT EXISTS auf_revenue_lots_fifo_idx
    ON auf_revenue_lots (workspace_id, created_at, id)
    WHERE remaining_units > 0;

CREATE TABLE IF NOT EXISTS auf_task_charge_lot_allocations (
    task_id UUID NOT NULL REFERENCES auf_task_charges(task_id) ON DELETE CASCADE,
    lot_id BIGINT NOT NULL REFERENCES auf_revenue_lots(id),
    allocated_units BIGINT NOT NULL CHECK (allocated_units > 0),
    allocated_revenue_usd NUMERIC(20, 8) NOT NULL CHECK (allocated_revenue_usd >= 0),
    basis_quality VARCHAR(16) NOT NULL
        CHECK (basis_quality IN ('actual', 'estimated', 'zero')),
    status VARCHAR(16) NOT NULL DEFAULT 'reserved'
        CHECK (status IN ('reserved', 'captured', 'restored')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (task_id, lot_id)
);

CREATE TABLE IF NOT EXISTS auf_generation_pnl (
    task_id UUID PRIMARY KEY REFERENCES auf_task_charges(task_id) ON DELETE RESTRICT,
    workspace_id BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    price_version_id BIGINT NOT NULL REFERENCES auf_price_versions(id),
    model_alias VARCHAR(96) NOT NULL,
    quoted_units BIGINT NOT NULL CHECK (quoted_units > 0),
    captured_units BIGINT NOT NULL CHECK (captured_units > 0),
    realized_revenue_usd NUMERIC(20, 8) NOT NULL CHECK (realized_revenue_usd >= 0),
    provider_cost_usd NUMERIC(20, 8) NOT NULL CHECK (provider_cost_usd > 0),
    operational_reserve_usd NUMERIC(20, 8) NOT NULL CHECK (operational_reserve_usd >= 0),
    contribution_profit_usd NUMERIC(20, 8) NOT NULL,
    contribution_margin_percent NUMERIC(12, 4),
    subsidy_usd NUMERIC(20, 8) NOT NULL CHECK (subsidy_usd >= 0),
    target_margin_percent NUMERIC(8, 4),
    pricing_strategy VARCHAR(24) NOT NULL,
    revenue_basis_quality VARCHAR(16) NOT NULL
        CHECK (revenue_basis_quality IN ('actual', 'estimated', 'zero', 'mixed')),
    captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS auf_generation_pnl_captured_idx
    ON auf_generation_pnl (captured_at DESC);
CREATE INDEX IF NOT EXISTS auf_generation_pnl_workspace_idx
    ON auf_generation_pnl (workspace_id, captured_at DESC);

CREATE OR REPLACE FUNCTION auf_effective_operational_reserve_percent()
RETURNS NUMERIC
LANGUAGE SQL
STABLE
AS $$
    WITH settings AS (
        SELECT operational_cost_buffer_percent,
               dynamic_reserve_enabled,
               dynamic_reserve_cap_percent
        FROM auf_economy_settings
        WHERE singleton_id = 1
    ), variance AS (
        SELECT percentile_cont(0.90) WITHIN GROUP (
                   ORDER BY GREATEST(
                       (actual_provider_cost_usd - provider_cost_usd)
                       / NULLIF(provider_cost_usd, 0) * 100,
                       0
                   )
               ) AS p90_positive_variance
        FROM auf_task_charges
        WHERE status = 'captured'
          AND actual_provider_cost_usd IS NOT NULL
          AND provider_cost_usd > 0
          AND updated_at >= NOW() - INTERVAL '30 days'
    )
    SELECT CASE
        WHEN NOT settings.dynamic_reserve_enabled
            THEN settings.operational_cost_buffer_percent
        ELSE LEAST(
            settings.dynamic_reserve_cap_percent,
            GREATEST(
                settings.operational_cost_buffer_percent,
                COALESCE(variance.p90_positive_variance, 0)
            )
        )
    END
    FROM settings CROSS JOIN variance;
$$;

CREATE OR REPLACE FUNCTION create_auf_revenue_lot_from_wallet_entry()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    revenue NUMERIC(20, 8);
    quality VARCHAR(16);
    lot_type VARCHAR(24);
BEGIN
    IF NEW.amount_units <= 0
       OR NEW.operation_type NOT IN ('purchase', 'grant', 'adjustment') THEN
        RETURN NEW;
    END IF;

    IF NEW.operation_type = 'purchase' THEN
        SELECT package_price_usd INTO revenue
        FROM auf_purchase_invoices
        WHERE id = NEW.invoice_id;
        IF revenue IS NULL THEN
            RAISE EXCEPTION 'Paid Auf purchase entry % has no invoice revenue basis', NEW.id;
        END IF;
        quality := 'actual';
        lot_type := 'purchase';
    ELSIF NEW.operation_type = 'grant' THEN
        revenue := 0;
        quality := 'zero';
        lot_type := 'grant';
    ELSE
        SELECT (NEW.amount_units::NUMERIC / 10000)
               * retail_auf_usd
        INTO revenue
        FROM auf_economy_settings
        WHERE singleton_id = 1;
        revenue := COALESCE(revenue, 0);
        quality := 'estimated';
        lot_type := 'adjustment';
    END IF;

    INSERT INTO auf_revenue_lots (
        workspace_id, source_entry_id, source_invoice_id,
        source_type, basis_quality, original_units, remaining_units,
        gross_revenue_usd, remaining_revenue_usd, created_at
    )
    VALUES (
        NEW.workspace_id, NEW.id, NEW.invoice_id,
        lot_type, quality, NEW.amount_units, NEW.amount_units,
        revenue, revenue, NEW.created_at
    )
    ON CONFLICT (source_entry_id) DO NOTHING;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS auf_wallet_entry_revenue_lot ON auf_wallet_entries;
CREATE TRIGGER auf_wallet_entry_revenue_lot
AFTER INSERT ON auf_wallet_entries
FOR EACH ROW
EXECUTE FUNCTION create_auf_revenue_lot_from_wallet_entry();

-- Existing balances predate revenue lots. Preserve them as explicitly estimated
-- basis rather than pretending their historical package mix is known.
INSERT INTO auf_revenue_lots (
    workspace_id, source_type, basis_quality,
    original_units, remaining_units,
    gross_revenue_usd, remaining_revenue_usd, created_at
)
SELECT wallet.workspace_id,
       'legacy_estimate',
       'estimated',
       wallet.available_units + wallet.reserved_units,
       wallet.available_units + wallet.reserved_units,
       ((wallet.available_units + wallet.reserved_units)::NUMERIC / 10000)
           * settings.quote_rub_per_vl / settings.billing_usd_to_rub,
       ((wallet.available_units + wallet.reserved_units)::NUMERIC / 10000)
           * settings.quote_rub_per_vl / settings.billing_usd_to_rub,
       NOW()
FROM auf_wallets AS wallet
CROSS JOIN auf_economy_settings AS settings
WHERE settings.singleton_id = 1
  AND wallet.available_units + wallet.reserved_units > 0
  AND NOT EXISTS (
      SELECT 1 FROM auf_revenue_lots AS lot
      WHERE lot.workspace_id = wallet.workspace_id
  );

CREATE OR REPLACE FUNCTION allocate_auf_charge_revenue(charge_task_id UUID)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    charge auf_task_charges%ROWTYPE;
    lot auf_revenue_lots%ROWTYPE;
    needed BIGINT;
    take_units BIGINT;
    take_revenue NUMERIC(20, 8);
BEGIN
    SELECT * INTO charge
    FROM auf_task_charges
    WHERE task_id = charge_task_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Auf charge % is missing for revenue allocation', charge_task_id;
    END IF;
    IF EXISTS (
        SELECT 1 FROM auf_task_charge_lot_allocations
        WHERE task_id = charge_task_id
    ) THEN
        RETURN;
    END IF;

    needed := charge.quoted_units;
    FOR lot IN
        SELECT *
        FROM auf_revenue_lots
        WHERE workspace_id = charge.workspace_id
          AND remaining_units > 0
        ORDER BY created_at, id
        FOR UPDATE
    LOOP
        EXIT WHEN needed = 0;
        take_units := LEAST(needed, lot.remaining_units);
        IF take_units = lot.remaining_units THEN
            take_revenue := lot.remaining_revenue_usd;
        ELSE
            take_revenue := ROUND(
                lot.remaining_revenue_usd
                * take_units::NUMERIC / lot.remaining_units::NUMERIC,
                8
            );
        END IF;

        UPDATE auf_revenue_lots
        SET remaining_units = remaining_units - take_units,
            remaining_revenue_usd = remaining_revenue_usd - take_revenue
        WHERE id = lot.id;

        INSERT INTO auf_task_charge_lot_allocations (
            task_id, lot_id, allocated_units,
            allocated_revenue_usd, basis_quality
        )
        VALUES (
            charge_task_id, lot.id, take_units,
            take_revenue, lot.basis_quality
        );
        needed := needed - take_units;
    END LOOP;

    IF needed <> 0 THEN
        RAISE EXCEPTION
            'Auf revenue lots cover % fewer units than charge % requires',
            needed, charge_task_id;
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION allocate_auf_charge_revenue_on_insert()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    PERFORM allocate_auf_charge_revenue(NEW.task_id);
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS auf_task_charge_revenue_allocation ON auf_task_charges;
CREATE TRIGGER auf_task_charge_revenue_allocation
AFTER INSERT ON auf_task_charges
FOR EACH ROW
EXECUTE FUNCTION allocate_auf_charge_revenue_on_insert();

DO $$
DECLARE
    charge_row RECORD;
BEGIN
    FOR charge_row IN
        SELECT task_id
        FROM auf_task_charges
        WHERE status = 'reserved'
        ORDER BY created_at, task_id
    LOOP
        PERFORM allocate_auf_charge_revenue(charge_row.task_id);
    END LOOP;
END;
$$;

CREATE OR REPLACE FUNCTION settle_auf_task_charge()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    charge auf_task_charges%ROWTYPE;
    wallet auf_wallets%ROWTYPE;
    restored BIGINT;
    entry_operation VARCHAR(32);
    entry_amount BIGINT;
    final_charge_status VARCHAR(24);
    revenue NUMERIC(20, 8);
    provider_cost NUMERIC(20, 8);
    profit NUMERIC(20, 8);
    margin_percent NUMERIC(12, 4);
    subsidy NUMERIC(20, 8);
    basis_quality VARCHAR(16);
BEGIN
    IF NEW.status = OLD.status OR NEW.status NOT IN ('success', 'error', 'cancelled') THEN
        RETURN NEW;
    END IF;

    SELECT * INTO charge
    FROM auf_task_charges
    WHERE task_id = NEW.id
    FOR UPDATE;
    IF NOT FOUND OR charge.status <> 'reserved' THEN
        RETURN NEW;
    END IF;

    SELECT * INTO wallet
    FROM auf_wallets
    WHERE workspace_id = charge.workspace_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Auf wallet % is missing for charged task %',
            charge.workspace_id, NEW.id;
    END IF;
    IF wallet.reserved_units < charge.reserved_units THEN
        RAISE EXCEPTION 'Auf reserved balance mismatch for task %', NEW.id;
    END IF;

    restored := CASE WHEN NEW.status = 'success' THEN 0 ELSE charge.reserved_units END;
    entry_operation := CASE
        WHEN NEW.status = 'success' THEN 'capture'
        WHEN NEW.status = 'error' THEN 'refund'
        ELSE 'release'
    END;
    entry_amount := CASE
        WHEN NEW.status = 'success' THEN -charge.reserved_units
        ELSE charge.reserved_units
    END;
    final_charge_status := CASE
        WHEN NEW.status = 'success' THEN 'captured'
        WHEN NEW.status = 'error' THEN 'refunded'
        ELSE 'released'
    END;

    UPDATE auf_wallets
    SET available_units = available_units + restored,
        reserved_units = reserved_units - charge.reserved_units,
        updated_at = NOW()
    WHERE workspace_id = charge.workspace_id
    RETURNING * INTO wallet;

    UPDATE auf_task_charges
    SET reserved_units = 0,
        captured_units = CASE
            WHEN NEW.status = 'success' THEN quoted_units
            ELSE captured_units
        END,
        refunded_units = CASE
            WHEN NEW.status IN ('error', 'cancelled') THEN quoted_units
            ELSE refunded_units
        END,
        actual_provider_cost_usd = CASE
            WHEN NEW.status = 'success'
                THEN COALESCE(actual_provider_cost_usd, provider_cost_usd)
            ELSE actual_provider_cost_usd
        END,
        status = final_charge_status,
        updated_at = NOW()
    WHERE task_id = NEW.id
    RETURNING * INTO charge;

    IF NEW.status = 'success' THEN
        UPDATE auf_task_charge_lot_allocations
        SET status = 'captured', updated_at = NOW()
        WHERE task_id = NEW.id AND status = 'reserved';

        SELECT COALESCE(SUM(allocated_revenue_usd), 0),
               CASE
                   WHEN COUNT(DISTINCT basis_quality) > 1 THEN 'mixed'
                   ELSE COALESCE(MIN(basis_quality), 'zero')
               END
        INTO revenue, basis_quality
        FROM auf_task_charge_lot_allocations
        WHERE task_id = NEW.id;

        provider_cost := COALESCE(
            charge.actual_provider_cost_usd,
            charge.provider_cost_usd
        );
        profit := revenue - provider_cost - charge.operational_reserve_usd;
        margin_percent := CASE
            WHEN revenue > 0 THEN ROUND(profit / revenue * 100, 4)
            ELSE NULL
        END;
        subsidy := GREATEST(provider_cost + charge.operational_reserve_usd - revenue, 0);

        INSERT INTO auf_generation_pnl (
            task_id, workspace_id, price_version_id, model_alias,
            quoted_units, captured_units, realized_revenue_usd,
            provider_cost_usd, operational_reserve_usd,
            contribution_profit_usd, contribution_margin_percent,
            subsidy_usd, target_margin_percent, pricing_strategy,
            revenue_basis_quality, captured_at
        )
        SELECT charge.task_id, charge.workspace_id, charge.price_version_id,
               price.model_alias, charge.quoted_units, charge.captured_units,
               revenue, provider_cost, charge.operational_reserve_usd,
               profit, margin_percent, subsidy, charge.target_margin_percent,
               charge.pricing_strategy, basis_quality, NOW()
        FROM auf_price_versions AS price
        WHERE price.id = charge.price_version_id
        ON CONFLICT (task_id) DO NOTHING;
    ELSE
        UPDATE auf_revenue_lots AS lot
        SET remaining_units = lot.remaining_units + allocation.allocated_units,
            remaining_revenue_usd = lot.remaining_revenue_usd
                + allocation.allocated_revenue_usd
        FROM auf_task_charge_lot_allocations AS allocation
        WHERE allocation.task_id = NEW.id
          AND allocation.status = 'reserved'
          AND lot.id = allocation.lot_id;

        UPDATE auf_task_charge_lot_allocations
        SET status = 'restored', updated_at = NOW()
        WHERE task_id = NEW.id AND status = 'reserved';
    END IF;

    INSERT INTO auf_wallet_entries (
        workspace_id, operation_type, amount_units,
        available_after_units, reserved_after_units,
        actor_user_id, task_id, idempotency_key, comment, metadata
    )
    VALUES (
        charge.workspace_id,
        entry_operation,
        entry_amount,
        wallet.available_units,
        wallet.reserved_units,
        NEW.created_by,
        NEW.id,
        'task:' || NEW.id::TEXT || ':' || entry_operation,
        CASE
            WHEN NEW.status = 'success' THEN 'Списание за успешную генерацию.'
            WHEN NEW.status = 'error' THEN 'Возврат после ошибки без результата.'
            ELSE 'Возврат после отмены задачи.'
        END,
        jsonb_build_object(
            'task_status', NEW.status,
            'realized_revenue_usd', CASE WHEN NEW.status = 'success' THEN revenue ELSE NULL END,
            'provider_cost_usd', CASE WHEN NEW.status = 'success' THEN provider_cost ELSE NULL END,
            'contribution_profit_usd', CASE WHEN NEW.status = 'success' THEN profit ELSE NULL END
        )
    )
    ON CONFLICT (idempotency_key) DO NOTHING;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS auf_task_charge_settlement ON ai_tasks;
CREATE TRIGGER auf_task_charge_settlement
AFTER UPDATE OF status ON ai_tasks
FOR EACH ROW
EXECUTE FUNCTION settle_auf_task_charge();

CREATE OR REPLACE VIEW auf_generation_margin_daily AS
SELECT date_trunc('day', pnl.captured_at) AS day,
       pnl.workspace_id,
       pnl.model_alias,
       COUNT(*) AS generations,
       SUM(pnl.captured_units) AS captured_units,
       SUM(pnl.realized_revenue_usd) AS realized_revenue_usd,
       SUM(pnl.provider_cost_usd) AS provider_cost_usd,
       SUM(pnl.operational_reserve_usd) AS operational_reserve_usd,
       SUM(pnl.contribution_profit_usd) AS contribution_profit_usd,
       CASE
           WHEN SUM(pnl.realized_revenue_usd) > 0
               THEN SUM(pnl.contribution_profit_usd)
                    / SUM(pnl.realized_revenue_usd) * 100
           ELSE NULL
       END AS contribution_margin_percent,
       SUM(pnl.subsidy_usd) AS subsidy_usd,
       COUNT(*) FILTER (WHERE pnl.subsidy_usd > 0) AS subsidized_generations,
       COUNT(*) FILTER (WHERE pnl.revenue_basis_quality <> 'actual') AS estimated_basis_generations
FROM auf_generation_pnl AS pnl
GROUP BY date_trunc('day', pnl.captured_at), pnl.workspace_id, pnl.model_alias;
