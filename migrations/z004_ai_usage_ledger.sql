CREATE TABLE IF NOT EXISTS ai_runtime_state (
    singleton_id SMALLINT PRIMARY KEY DEFAULT 1,
    paused BOOLEAN NOT NULL DEFAULT FALSE,
    pause_reason TEXT,
    updated_by BIGINT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ai_runtime_state_singleton_check CHECK (singleton_id = 1)
);

INSERT INTO ai_runtime_state (singleton_id)
VALUES (1)
ON CONFLICT (singleton_id) DO NOTHING;

CREATE TABLE IF NOT EXISTS ai_usage_events (
    id BIGSERIAL PRIMARY KEY,
    request_id UUID NOT NULL UNIQUE,
    scope VARCHAR(24) NOT NULL,
    provider VARCHAR(80) NOT NULL,
    model VARCHAR(160) NOT NULL,
    operation VARCHAR(80) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'reserved',
    estimated_cost_rub NUMERIC(14, 4) NOT NULL DEFAULT 0,
    actual_cost_rub NUMERIC(14, 4) NOT NULL DEFAULT 0,
    input_tokens BIGINT NOT NULL DEFAULT 0,
    output_tokens BIGINT NOT NULL DEFAULT 0,
    latency_ms BIGINT,
    user_id BIGINT,
    chat_id BIGINT,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    error_type VARCHAR(160),
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    CONSTRAINT ai_usage_events_scope_check
        CHECK (scope IN ('vision', 'roleplay', 'hermes', 'codex')),
    CONSTRAINT ai_usage_events_status_check
        CHECK (status IN ('reserved', 'success', 'error', 'cancelled')),
    CONSTRAINT ai_usage_events_cost_check
        CHECK (estimated_cost_rub >= 0 AND actual_cost_rub >= 0),
    CONSTRAINT ai_usage_events_tokens_check
        CHECK (input_tokens >= 0 AND output_tokens >= 0),
    CONSTRAINT ai_usage_events_operation_check
        CHECK (LENGTH(BTRIM(operation)) > 0),
    CONSTRAINT ai_usage_events_provider_check
        CHECK (LENGTH(BTRIM(provider)) > 0),
    CONSTRAINT ai_usage_events_model_check
        CHECK (LENGTH(BTRIM(model)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_ai_usage_events_created_at
    ON ai_usage_events(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ai_usage_events_scope_created_at
    ON ai_usage_events(scope, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ai_usage_events_active_reservations
    ON ai_usage_events(created_at)
    WHERE status = 'reserved';

CREATE TABLE IF NOT EXISTS ai_tasks (
    id UUID PRIMARY KEY,
    scope VARCHAR(24) NOT NULL,
    task_type VARCHAR(80) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'queued',
    priority SMALLINT NOT NULL DEFAULT 100,
    payload JSONB NOT NULL DEFAULT '{}'::JSONB,
    dedupe_key VARCHAR(200),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 2,
    not_before TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    locked_by VARCHAR(120),
    locked_at TIMESTAMPTZ,
    last_error TEXT,
    created_by BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    CONSTRAINT ai_tasks_scope_check
        CHECK (scope IN ('vision', 'roleplay', 'hermes', 'codex')),
    CONSTRAINT ai_tasks_status_check
        CHECK (status IN ('queued', 'running', 'success', 'error', 'cancelled')),
    CONSTRAINT ai_tasks_priority_check CHECK (priority BETWEEN 0 AND 1000),
    CONSTRAINT ai_tasks_attempts_check
        CHECK (attempt_count >= 0 AND max_attempts BETWEEN 1 AND 20),
    CONSTRAINT ai_tasks_type_check CHECK (LENGTH(BTRIM(task_type)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_ai_tasks_claim
    ON ai_tasks(priority, not_before, created_at)
    WHERE status = 'queued';

CREATE INDEX IF NOT EXISTS idx_ai_tasks_status_updated
    ON ai_tasks(status, updated_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_tasks_active_dedupe
    ON ai_tasks(dedupe_key)
    WHERE dedupe_key IS NOT NULL
      AND status IN ('queued', 'running');
