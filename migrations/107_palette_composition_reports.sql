CREATE TABLE IF NOT EXISTS palette_composition_reports (
    id BIGSERIAL PRIMARY KEY,
    result_file_id TEXT NOT NULL,
    result_file_unique_id TEXT,
    provider VARCHAR(64) NOT NULL,
    model VARCHAR(160) NOT NULL,
    analysis_version SMALLINT NOT NULL DEFAULT 1,
    width INTEGER NOT NULL CHECK (width > 0),
    height INTEGER NOT NULL CHECK (height > 0),
    palette JSONB NOT NULL,
    composition_score SMALLINT NOT NULL CHECK (composition_score BETWEEN 0 AND 100),
    balance_score SMALLINT NOT NULL CHECK (balance_score BETWEEN 0 AND 100),
    framing_score SMALLINT NOT NULL CHECK (framing_score BETWEEN 0 AND 100),
    hierarchy_score SMALLINT NOT NULL CHECK (hierarchy_score BETWEEN 0 AND 100),
    depth_score SMALLINT NOT NULL CHECK (depth_score BETWEEN 0 AND 100),
    lighting_score SMALLINT NOT NULL CHECK (lighting_score BETWEEN 0 AND 100),
    palette_harmony_score SMALLINT NOT NULL CHECK (palette_harmony_score BETWEEN 0 AND 100),
    confidence SMALLINT NOT NULL CHECK (confidence BETWEEN 0 AND 100),
    verdict VARCHAR(24) NOT NULL CHECK (
        verdict IN ('strong', 'review', 'weak', 'insufficient')
    ),
    report JSONB NOT NULL,
    created_by BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_palette_composition_created
    ON palette_composition_reports (created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_palette_composition_creator_created
    ON palette_composition_reports (created_by, created_at DESC)
    WHERE created_by IS NOT NULL;
