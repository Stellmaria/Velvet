CREATE TABLE IF NOT EXISTS meow_price_versions (
    id BIGSERIAL PRIMARY KEY,
    version_key VARCHAR(160) NOT NULL UNIQUE,
    provider VARCHAR(16) NOT NULL CHECK (provider IN ('kie', 'grs')),
    model_alias VARCHAR(96) NOT NULL,
    operation VARCHAR(64) NOT NULL DEFAULT 'media.generate',
    resolution VARCHAR(24),
    audio BOOLEAN,
    pricing_basis VARCHAR(24) NOT NULL
        CHECK (pricing_basis IN ('fixed', 'per_second')),
    unit_cost_usd NUMERIC(18, 8) NOT NULL CHECK (unit_cost_usd > 0),
    extra_reference_cost_usd NUMERIC(18, 8) NOT NULL DEFAULT 0
        CHECK (extra_reference_cost_usd >= 0),
    effective_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    effective_to TIMESTAMPTZ,
    source TEXT NOT NULL,
    approved_by_user_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (effective_to IS NULL OR effective_to > effective_from)
);

CREATE INDEX IF NOT EXISTS meow_price_versions_lookup_idx
    ON meow_price_versions (
        model_alias,
        operation,
        resolution,
        audio,
        effective_from DESC
    );

CREATE TABLE IF NOT EXISTS meow_task_charges (
    -- Keep the financial record even if an operational ai_task is pruned.
    -- The UUID remains the immutable logical link without a destructive FK.
    task_id UUID PRIMARY KEY,
    workspace_id BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    price_version_id BIGINT NOT NULL REFERENCES meow_price_versions(id),
    quoted_units BIGINT NOT NULL CHECK (quoted_units > 0),
    reserved_units BIGINT NOT NULL CHECK (reserved_units >= 0),
    captured_units BIGINT NOT NULL DEFAULT 0 CHECK (captured_units >= 0),
    refunded_units BIGINT NOT NULL DEFAULT 0 CHECK (refunded_units >= 0),
    provider_cost_usd NUMERIC(18, 8) NOT NULL CHECK (provider_cost_usd > 0),
    status VARCHAR(24) NOT NULL DEFAULT 'reserved'
        CHECK (status IN ('reserved', 'captured', 'released', 'refunded')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (reserved_units + captured_units + refunded_units = quoted_units)
);

CREATE INDEX IF NOT EXISTS meow_task_charges_workspace_idx
    ON meow_task_charges (workspace_id, created_at DESC);

INSERT INTO meow_price_versions (
    version_key, provider, model_alias, resolution, audio,
    pricing_basis, unit_cost_usd, extra_reference_cost_usd, source
)
VALUES
    ('2026-07-30:nano-banana-2', 'grs', 'nano_banana_2', NULL, NULL,
     'fixed', 0.02000000, 0, 'Approved GRS estimate: 1200 credits / $0.02'),
    ('2026-07-30:nano-banana-pro', 'grs', 'nano_banana_pro', NULL, NULL,
     'fixed', 0.03000000, 0, 'Approved GRS estimate: 1800 credits / $0.03'),
    ('2026-07-30:seedream-5-pro:1k', 'kie', 'seedream_5_pro', '1K', NULL,
     'fixed', 0.07500000, 0.00500000, 'Approved Kie price; extra reference after first is $0.005'),
    ('2026-07-30:seedream-5-pro:2k', 'kie', 'seedream_5_pro', '2K', NULL,
     'fixed', 0.15000000, 0.00500000, 'Approved Kie price; extra reference after first is $0.005'),
    ('2026-07-30:qwen-image-2:2k', 'kie', 'qwen2_image_edit', '2K', NULL,
     'fixed', 0.02000000, 0, 'Approved preflight estimate'),
    ('2026-07-30:wan-2-7-image:1k', 'kie', 'wan_27_image', '1K', NULL,
     'fixed', 0.05000000, 0, 'Approved preflight estimate'),
    ('2026-07-30:wan-2-7-image:2k', 'kie', 'wan_27_image', '2K', NULL,
     'fixed', 0.08000000, 0, 'Approved preflight estimate'),
    ('2026-07-30:flux-2-pro:1k', 'kie', 'flux_2_pro_image', '1K', NULL,
     'fixed', 0.04500000, 0, 'Approved preflight estimate'),
    ('2026-07-30:flux-2-pro:2k', 'kie', 'flux_2_pro_image', '2K', NULL,
     'fixed', 0.07500000, 0, 'Approved preflight estimate'),
    ('2026-07-30:grok-v1:480p', 'kie', 'grok_imagine_video', '480p', NULL,
     'per_second', 0.00800000, 0, 'Approved Kie per-second price'),
    ('2026-07-30:grok-v1:720p', 'kie', 'grok_imagine_video', '720p', NULL,
     'per_second', 0.01500000, 0, 'Approved Kie per-second price'),
    ('2026-07-30:grok-1-5:480p', 'kie', 'grok_imagine_video_15', '480p', NULL,
     'per_second', 0.07250000, 0, 'Approved Kie per-second estimate'),
    ('2026-07-30:grok-1-5:720p', 'kie', 'grok_imagine_video_15', '720p', NULL,
     'per_second', 0.12500000, 0, 'Approved Kie per-second estimate'),
    ('2026-07-30:seedance:480p:no-audio', 'kie', 'seedance_15_pro_video', '480p', FALSE,
     'per_second', 0.00875000, 0, 'Approved Kie per-second estimate'),
    ('2026-07-30:seedance:720p:no-audio', 'kie', 'seedance_15_pro_video', '720p', FALSE,
     'per_second', 0.01750000, 0, 'Approved Kie per-second estimate'),
    ('2026-07-30:seedance:1080p:no-audio', 'kie', 'seedance_15_pro_video', '1080p', FALSE,
     'per_second', 0.03750000, 0, 'Approved Kie per-second estimate'),
    ('2026-07-30:seedance:480p:audio', 'kie', 'seedance_15_pro_video', '480p', TRUE,
     'per_second', 0.01750000, 0, 'Approved Kie per-second estimate'),
    ('2026-07-30:seedance:720p:audio', 'kie', 'seedance_15_pro_video', '720p', TRUE,
     'per_second', 0.03500000, 0, 'Approved Kie per-second estimate'),
    ('2026-07-30:seedance:1080p:audio', 'kie', 'seedance_15_pro_video', '1080p', TRUE,
     'per_second', 0.07500000, 0, 'Approved Kie per-second estimate'),
    ('2026-07-30:wan-2-7-video:720p', 'kie', 'wan_26_image_to_video', '720p', NULL,
     'per_second', 0.08000000, 0, 'Approved Kie per-second estimate'),
    ('2026-07-30:wan-2-7-video:1080p', 'kie', 'wan_26_image_to_video', '1080p', NULL,
     'per_second', 0.12000000, 0, 'Approved Kie per-second estimate')
ON CONFLICT (version_key) DO NOTHING;

CREATE OR REPLACE FUNCTION settle_meow_task_charge()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    charge meow_task_charges%ROWTYPE;
    wallet meow_wallets%ROWTYPE;
    restored BIGINT;
    entry_operation VARCHAR(32);
    entry_amount BIGINT;
    final_charge_status VARCHAR(24);
BEGIN
    IF NEW.status = OLD.status OR NEW.status NOT IN ('success', 'error', 'cancelled') THEN
        RETURN NEW;
    END IF;

    SELECT * INTO charge
    FROM meow_task_charges
    WHERE task_id = NEW.id
    FOR UPDATE;

    IF NOT FOUND OR charge.status <> 'reserved' THEN
        RETURN NEW;
    END IF;

    SELECT * INTO wallet
    FROM meow_wallets
    WHERE workspace_id = charge.workspace_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Meow wallet % is missing for charged task %',
            charge.workspace_id, NEW.id;
    END IF;
    IF wallet.reserved_units < charge.reserved_units THEN
        RAISE EXCEPTION 'Meow reserved balance mismatch for task %', NEW.id;
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

    UPDATE meow_wallets
    SET available_units = available_units + restored,
        reserved_units = reserved_units - charge.reserved_units,
        updated_at = NOW()
    WHERE workspace_id = charge.workspace_id
    RETURNING * INTO wallet;

    UPDATE meow_task_charges
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

    INSERT INTO meow_wallet_entries (
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

DROP TRIGGER IF EXISTS meow_task_charge_settlement ON ai_tasks;
CREATE TRIGGER meow_task_charge_settlement
AFTER UPDATE OF status ON ai_tasks
FOR EACH ROW
EXECUTE FUNCTION settle_meow_task_charge();

CREATE OR REPLACE FUNCTION guard_meow_charged_task_requeue()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.status IN ('success', 'error', 'cancelled')
       AND NEW.status = 'queued'
       AND EXISTS (
           SELECT 1 FROM meow_task_charges WHERE task_id = OLD.id
       ) THEN
        RAISE EXCEPTION 'Charged Meow tasks must be recreated with a fresh price quote';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS meow_charged_task_requeue_guard ON ai_tasks;
CREATE TRIGGER meow_charged_task_requeue_guard
BEFORE UPDATE OF status ON ai_tasks
FOR EACH ROW
EXECUTE FUNCTION guard_meow_charged_task_requeue();
