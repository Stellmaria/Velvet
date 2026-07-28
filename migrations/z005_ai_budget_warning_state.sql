ALTER TABLE ai_runtime_state
    ADD COLUMN IF NOT EXISTS warning_month DATE,
    ADD COLUMN IF NOT EXISTS warning_percent SMALLINT;

ALTER TABLE ai_runtime_state
    ADD CONSTRAINT ai_runtime_state_warning_percent_check
    CHECK (warning_percent IS NULL OR warning_percent BETWEEN 1 AND 99);
