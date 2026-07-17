CREATE TABLE IF NOT EXISTS ai_jobs (
    id BIGSERIAL PRIMARY KEY,
    kind VARCHAR(48) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    stage VARCHAR(32) NOT NULL DEFAULT 'queued',
    title VARCHAR(240) NOT NULL,
    provider VARCHAR(64),
    model VARCHAR(160),
    request_payload JSONB NOT NULL DEFAULT '{}'::JSONB,
    result_payload JSONB,
    result_text TEXT,
    result_reference_type VARCHAR(48),
    result_reference_id BIGINT,
    error_message TEXT,
    created_by BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ai_jobs_status_check CHECK (
        status IN ('pending', 'processing', 'ready', 'error')
    ),
    CONSTRAINT ai_jobs_kind_not_empty CHECK (BTRIM(kind) <> ''),
    CONSTRAINT ai_jobs_stage_not_empty CHECK (BTRIM(stage) <> '')
);

CREATE INDEX IF NOT EXISTS idx_ai_jobs_creator_created
    ON ai_jobs (created_by, created_at DESC, id DESC)
    WHERE created_by IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_ai_jobs_status_updated
    ON ai_jobs (status, updated_at, id);
