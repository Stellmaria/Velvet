CREATE TABLE IF NOT EXISTS prompt_result_comparison_reports (
    id BIGSERIAL PRIMARY KEY,
    result_file_id TEXT NOT NULL,
    result_file_unique_id TEXT,
    prompt_text TEXT NOT NULL,
    provider VARCHAR(64) NOT NULL,
    model VARCHAR(160) NOT NULL,
    analysis_version SMALLINT NOT NULL DEFAULT 1,
    overall_score SMALLINT NOT NULL CHECK (overall_score BETWEEN 0 AND 100),
    subject_score SMALLINT NOT NULL CHECK (subject_score BETWEEN 0 AND 100),
    composition_score SMALLINT NOT NULL CHECK (composition_score BETWEEN 0 AND 100),
    lighting_score SMALLINT NOT NULL CHECK (lighting_score BETWEEN 0 AND 100),
    palette_score SMALLINT NOT NULL CHECK (palette_score BETWEEN 0 AND 100),
    environment_score SMALLINT NOT NULL CHECK (environment_score BETWEEN 0 AND 100),
    style_score SMALLINT NOT NULL CHECK (style_score BETWEEN 0 AND 100),
    technical_score SMALLINT NOT NULL CHECK (technical_score BETWEEN 0 AND 100),
    confidence SMALLINT NOT NULL CHECK (confidence BETWEEN 0 AND 100),
    verdict VARCHAR(24) NOT NULL CHECK (
        verdict IN ('strong', 'partial', 'weak', 'insufficient')
    ),
    report JSONB NOT NULL,
    created_by BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_prompt_result_reports_created
    ON prompt_result_comparison_reports (created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_prompt_result_reports_creator_created
    ON prompt_result_comparison_reports (created_by, created_at DESC)
    WHERE created_by IS NOT NULL;
