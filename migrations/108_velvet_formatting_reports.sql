CREATE TABLE IF NOT EXISTS velvet_formatting_reports (
    id BIGSERIAL PRIMARY KEY,
    mode VARCHAR(16) NOT NULL CHECK (mode IN ('shell', 'short', 'full')),
    source_text TEXT NOT NULL,
    provider VARCHAR(64) NOT NULL,
    model VARCHAR(160) NOT NULL,
    analysis_version SMALLINT NOT NULL DEFAULT 1,
    payload JSONB NOT NULL,
    rendered_text TEXT NOT NULL,
    created_by BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_velvet_formatting_created
    ON velvet_formatting_reports (created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_velvet_formatting_mode_created
    ON velvet_formatting_reports (mode, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_velvet_formatting_creator_created
    ON velvet_formatting_reports (created_by, created_at DESC)
    WHERE created_by IS NOT NULL;
