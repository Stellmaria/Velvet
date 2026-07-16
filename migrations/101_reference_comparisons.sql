CREATE TABLE IF NOT EXISTS reference_comparison_reports (
    id BIGSERIAL PRIMARY KEY,
    character_id BIGINT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    reference_id BIGINT NOT NULL REFERENCES character_references(id) ON DELETE CASCADE,
    result_file_id TEXT NOT NULL,
    result_file_unique_id TEXT,
    provider VARCHAR(64) NOT NULL,
    model VARCHAR(160) NOT NULL,
    overall_score SMALLINT NOT NULL CHECK (overall_score BETWEEN 0 AND 100),
    face_score SMALLINT NOT NULL CHECK (face_score BETWEEN 0 AND 100),
    hair_score SMALLINT NOT NULL CHECK (hair_score BETWEEN 0 AND 100),
    body_score SMALLINT NOT NULL CHECK (body_score BETWEEN 0 AND 100),
    unique_traits_score SMALLINT NOT NULL CHECK (unique_traits_score BETWEEN 0 AND 100),
    confidence SMALLINT NOT NULL CHECK (confidence BETWEEN 0 AND 100),
    verdict VARCHAR(24) NOT NULL CHECK (
        verdict IN ('strong', 'partial', 'weak', 'insufficient')
    ),
    report JSONB NOT NULL,
    created_by BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reference_comparison_character_created
    ON reference_comparison_reports (character_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_reference_comparison_verdict_created
    ON reference_comparison_reports (verdict, created_at DESC);
