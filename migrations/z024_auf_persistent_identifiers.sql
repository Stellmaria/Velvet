-- Rename the deployed Meow storage contract to the canonical Auf vocabulary.
-- Historical z020-z023 files remain immutable because their checksums may already
-- be recorded in production databases.

DROP TRIGGER IF EXISTS meow_task_charge_settlement ON ai_tasks;
DROP TRIGGER IF EXISTS auf_task_charge_settlement ON ai_tasks;
DROP TRIGGER IF EXISTS meow_charged_task_requeue_guard ON ai_tasks;
DROP TRIGGER IF EXISTS auf_charged_task_requeue_guard ON ai_tasks;
DROP FUNCTION IF EXISTS settle_meow_task_charge();
DROP FUNCTION IF EXISTS settle_auf_task_charge();
DROP FUNCTION IF EXISTS guard_meow_charged_task_requeue();
DROP FUNCTION IF EXISTS guard_auf_charged_task_requeue();

DO $$
BEGIN
    IF to_regclass('meow_runtime_settings') IS NOT NULL
       AND to_regclass('auf_runtime_settings') IS NULL THEN
        ALTER TABLE meow_runtime_settings RENAME TO auf_runtime_settings;
    END IF;
    IF to_regclass('workspace_meow_settings') IS NOT NULL
       AND to_regclass('workspace_auf_settings') IS NULL THEN
        ALTER TABLE workspace_meow_settings RENAME TO workspace_auf_settings;
    END IF;
    IF to_regclass('meow_economy_settings') IS NOT NULL
       AND to_regclass('auf_economy_settings') IS NULL THEN
        ALTER TABLE meow_economy_settings RENAME TO auf_economy_settings;
    END IF;
    IF to_regclass('meow_wallets') IS NOT NULL
       AND to_regclass('auf_wallets') IS NULL THEN
        ALTER TABLE meow_wallets RENAME TO auf_wallets;
    END IF;
    IF to_regclass('meow_wallet_entries') IS NOT NULL
       AND to_regclass('auf_wallet_entries') IS NULL THEN
        ALTER TABLE meow_wallet_entries RENAME TO auf_wallet_entries;
    END IF;
    IF to_regclass('meow_price_versions') IS NOT NULL
       AND to_regclass('auf_price_versions') IS NULL THEN
        ALTER TABLE meow_price_versions RENAME TO auf_price_versions;
    END IF;
    IF to_regclass('meow_task_charges') IS NOT NULL
       AND to_regclass('auf_task_charges') IS NULL THEN
        ALTER TABLE meow_task_charges RENAME TO auf_task_charges;
    END IF;
    IF to_regclass('meow_purchase_invoices') IS NOT NULL
       AND to_regclass('auf_purchase_invoices') IS NULL THEN
        ALTER TABLE meow_purchase_invoices RENAME TO auf_purchase_invoices;
    END IF;
    IF to_regclass('meow_reconciliation_state') IS NOT NULL
       AND to_regclass('auf_reconciliation_state') IS NULL THEN
        ALTER TABLE meow_reconciliation_state RENAME TO auf_reconciliation_state;
    END IF;
END;
$$;

ALTER SEQUENCE IF EXISTS meow_wallet_entries_id_seq
    RENAME TO auf_wallet_entries_id_seq;
ALTER SEQUENCE IF EXISTS meow_price_versions_id_seq
    RENAME TO auf_price_versions_id_seq;

DO $$
DECLARE
    item RECORD;
    replacement TEXT;
BEGIN
    FOR item IN
        SELECT constraint_row.conrelid,
               constraint_row.conrelid::REGCLASS AS relation_name,
               constraint_row.conname
        FROM pg_constraint AS constraint_row
        WHERE constraint_row.conname LIKE 'meow\_%' ESCAPE '\'
    LOOP
        replacement := regexp_replace(item.conname, '^meow_', 'auf_');
        IF NOT EXISTS (
            SELECT 1
            FROM pg_constraint
            WHERE conrelid = item.conrelid
              AND conname = replacement
        ) THEN
            EXECUTE format(
                'ALTER TABLE %s RENAME CONSTRAINT %I TO %I',
                item.relation_name,
                item.conname,
                replacement
            );
        END IF;
    END LOOP;

    FOR item IN
        SELECT index_row.schemaname,
               index_row.indexname
        FROM pg_indexes AS index_row
        WHERE index_row.schemaname = current_schema()
          AND index_row.indexname LIKE 'meow\_%' ESCAPE '\'
    LOOP
        replacement := regexp_replace(item.indexname, '^meow_', 'auf_');
        IF to_regclass(format('%I.%I', item.schemaname, replacement)) IS NULL THEN
            EXECUTE format(
                'ALTER INDEX %I.%I RENAME TO %I',
                item.schemaname,
                item.indexname,
                replacement
            );
        END IF;
    END LOOP;
END;
$$;

-- The previous constraint only permits the historical module key, so remove it
-- before inserting canonical rows. Recreate it after the backfill is complete.
ALTER TABLE workspace_modules
    DROP CONSTRAINT IF EXISTS workspace_modules_module_key_check;

INSERT INTO workspace_modules (
    workspace_id, module_key, is_allowed, is_enabled,
    updated_by_user_id, created_at, updated_at
)
SELECT workspace_id, 'auf', is_allowed, is_enabled,
       updated_by_user_id, created_at, updated_at
FROM workspace_modules
WHERE module_key = 'meow'
ON CONFLICT (workspace_id, module_key) DO UPDATE
SET is_allowed = EXCLUDED.is_allowed,
    is_enabled = EXCLUDED.is_enabled,
    updated_by_user_id = EXCLUDED.updated_by_user_id,
    updated_at = GREATEST(workspace_modules.updated_at, EXCLUDED.updated_at);

DELETE FROM workspace_modules WHERE module_key = 'meow';

INSERT INTO workspace_user_module_preferences (
    workspace_id, user_id, module_key, is_visible, created_at, updated_at
)
SELECT workspace_id, user_id, 'auf', is_visible, created_at, updated_at
FROM workspace_user_module_preferences
WHERE module_key = 'meow'
ON CONFLICT (workspace_id, user_id, module_key) DO UPDATE
SET is_visible = EXCLUDED.is_visible,
    updated_at = GREATEST(
        workspace_user_module_preferences.updated_at,
        EXCLUDED.updated_at
    );

DELETE FROM workspace_user_module_preferences WHERE module_key = 'meow';

UPDATE workspace_creation_grants
SET allowed_modules = array_replace(allowed_modules, 'meow', 'auf'),
    updated_at = NOW()
WHERE 'meow' = ANY(allowed_modules);

ALTER TABLE workspace_modules
    ADD CONSTRAINT workspace_modules_module_key_check
    CHECK (
        module_key IN (
            'characters', 'archive', 'taxonomy', 'references',
            'public_archive', 'watermark', 'qwen', 'publications',
            'analytics', 'team', 'auf'
        )
    );

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
        status = final_charge_status,
        updated_at = NOW()
    WHERE task_id = NEW.id;

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
        jsonb_build_object('task_status', NEW.status)
    )
    ON CONFLICT (idempotency_key) DO NOTHING;

    RETURN NEW;
END;
$$;

CREATE TRIGGER auf_task_charge_settlement
AFTER UPDATE OF status ON ai_tasks
FOR EACH ROW
EXECUTE FUNCTION settle_auf_task_charge();

CREATE OR REPLACE FUNCTION guard_auf_charged_task_requeue()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.status IN ('success', 'error', 'cancelled')
       AND NEW.status = 'queued'
       AND EXISTS (
           SELECT 1 FROM auf_task_charges WHERE task_id = OLD.id
       ) THEN
        RAISE EXCEPTION 'Charged Auf tasks must be recreated with a fresh price quote';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER auf_charged_task_requeue_guard
BEFORE UPDATE OF status ON ai_tasks
FOR EACH ROW
EXECUTE FUNCTION guard_auf_charged_task_requeue();
