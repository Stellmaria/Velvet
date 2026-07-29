CREATE TABLE IF NOT EXISTS ai_task_batches (
    id UUID PRIMARY KEY,
    task_type VARCHAR(80) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'planned',
    candidate_ids JSONB NOT NULL DEFAULT '[]'::JSONB,
    candidate_count INTEGER NOT NULL DEFAULT 0,
    created_task_count INTEGER NOT NULL DEFAULT 0,
    deduplicated_task_count INTEGER NOT NULL DEFAULT 0,
    max_cost_per_item_rub NUMERIC(14, 4) NOT NULL DEFAULT 0,
    estimated_cost_rub NUMERIC(14, 4) NOT NULL DEFAULT 0,
    prompt_version INTEGER NOT NULL DEFAULT 1,
    created_by BIGINT,
    expires_at TIMESTAMPTZ NOT NULL,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    last_error TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ai_task_batches_type_check
        CHECK (LENGTH(BTRIM(task_type)) > 0),
    CONSTRAINT ai_task_batches_status_check
        CHECK (
            status IN (
                'planned', 'starting', 'queued', 'completed',
                'cancelled', 'expired', 'error'
            )
        ),
    CONSTRAINT ai_task_batches_candidate_ids_check
        CHECK (jsonb_typeof(candidate_ids) = 'array'),
    CONSTRAINT ai_task_batches_counts_check
        CHECK (
            candidate_count >= 0
            AND created_task_count >= 0
            AND deduplicated_task_count >= 0
            AND created_task_count + deduplicated_task_count <= candidate_count
        ),
    CONSTRAINT ai_task_batches_cost_check
        CHECK (max_cost_per_item_rub >= 0 AND estimated_cost_rub >= 0),
    CONSTRAINT ai_task_batches_prompt_version_check
        CHECK (prompt_version >= 1)
);

ALTER TABLE ai_tasks
    ADD COLUMN IF NOT EXISTS batch_id UUID REFERENCES ai_task_batches(id) ON DELETE SET NULL;

CREATE OR REPLACE FUNCTION assign_ai_task_batch_from_payload()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    payload_batch TEXT;
BEGIN
    IF NEW.batch_id IS NOT NULL OR NEW.payload IS NULL THEN
        RETURN NEW;
    END IF;

    payload_batch := NULLIF(BTRIM(NEW.payload->>'batch_id'), '');
    IF payload_batch IS NULL THEN
        RETURN NEW;
    END IF;

    NEW.batch_id := payload_batch::UUID;
    RETURN NEW;
EXCEPTION
    WHEN invalid_text_representation THEN
        RAISE EXCEPTION 'Invalid AI batch_id in task payload: %', payload_batch;
END;
$$;

DROP TRIGGER IF EXISTS trg_assign_ai_task_batch_from_payload ON ai_tasks;
CREATE TRIGGER trg_assign_ai_task_batch_from_payload
BEFORE INSERT OR UPDATE OF payload,batch_id ON ai_tasks
FOR EACH ROW
EXECUTE FUNCTION assign_ai_task_batch_from_payload();

CREATE INDEX IF NOT EXISTS idx_ai_task_batches_status_expires
    ON ai_task_batches(status, expires_at);

CREATE INDEX IF NOT EXISTS idx_ai_task_batches_created
    ON ai_task_batches(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ai_tasks_batch_id
    ON ai_tasks(batch_id)
    WHERE batch_id IS NOT NULL;
