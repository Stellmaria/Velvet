ALTER TABLE ai_tasks
    ADD COLUMN IF NOT EXISTS result JSONB NOT NULL DEFAULT '{}'::JSONB,
    ADD COLUMN IF NOT EXISTS estimated_cost_rub NUMERIC(14, 4) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS last_error_type VARCHAR(160),
    ADD COLUMN IF NOT EXISTS last_retry_delay_seconds INTEGER;

ALTER TABLE ai_tasks
    ADD CONSTRAINT ai_tasks_estimated_cost_check
    CHECK (estimated_cost_rub >= 0);

ALTER TABLE ai_tasks
    ADD CONSTRAINT ai_tasks_retry_delay_check
    CHECK (last_retry_delay_seconds IS NULL OR last_retry_delay_seconds >= 0);

CREATE INDEX IF NOT EXISTS idx_ai_tasks_running_locked
    ON ai_tasks(locked_at)
    WHERE status = 'running';

CREATE INDEX IF NOT EXISTS idx_ai_tasks_recent_terminal
    ON ai_tasks(completed_at DESC)
    WHERE status IN ('success', 'error', 'cancelled');
