-- PostgreSQL rejects an unqualified basis_quality reference because the
-- settlement function also used a local variable with the same name.
-- Recreate the trigger function with an explicit allocation alias and a
-- distinct result variable before the feature reaches production.

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
    resolved_basis_quality VARCHAR(16);
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

        SELECT COALESCE(SUM(allocation.allocated_revenue_usd), 0),
               CASE
                   WHEN COUNT(DISTINCT allocation.basis_quality) > 1 THEN 'mixed'
                   ELSE COALESCE(MIN(allocation.basis_quality), 'zero')
               END
        INTO revenue, resolved_basis_quality
        FROM auf_task_charge_lot_allocations AS allocation
        WHERE allocation.task_id = NEW.id;

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
               charge.pricing_strategy, resolved_basis_quality, NOW()
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
