CREATE TABLE IF NOT EXISTS media_set_ai_reports (
    id BIGSERIAL PRIMARY KEY,
    media_set_id BIGINT NOT NULL REFERENCES media_sets(id) ON DELETE CASCADE,
    provider VARCHAR(64) NOT NULL,
    model VARCHAR(160) NOT NULL,
    analysis_version SMALLINT NOT NULL DEFAULT 1,
    item_count SMALLINT NOT NULL CHECK (item_count BETWEEN 2 AND 12),
    overall_score SMALLINT NOT NULL CHECK (overall_score BETWEEN 0 AND 100),
    style_score SMALLINT NOT NULL CHECK (style_score BETWEEN 0 AND 100),
    lighting_score SMALLINT NOT NULL CHECK (lighting_score BETWEEN 0 AND 100),
    palette_score SMALLINT NOT NULL CHECK (palette_score BETWEEN 0 AND 100),
    environment_score SMALLINT NOT NULL CHECK (environment_score BETWEEN 0 AND 100),
    composition_score SMALLINT NOT NULL CHECK (composition_score BETWEEN 0 AND 100),
    narrative_score SMALLINT NOT NULL CHECK (narrative_score BETWEEN 0 AND 100),
    character_continuity_score SMALLINT NOT NULL CHECK (
        character_continuity_score BETWEEN 0 AND 100
    ),
    technical_score SMALLINT NOT NULL CHECK (technical_score BETWEEN 0 AND 100),
    confidence SMALLINT NOT NULL CHECK (confidence BETWEEN 0 AND 100),
    verdict VARCHAR(24) NOT NULL CHECK (
        verdict IN ('coherent', 'review', 'incoherent', 'insufficient')
    ),
    report JSONB NOT NULL,
    created_by BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_media_set_ai_reports_set_created
    ON media_set_ai_reports (media_set_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_media_set_ai_reports_verdict_created
    ON media_set_ai_reports (verdict, created_at DESC);
