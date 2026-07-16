CREATE TABLE IF NOT EXISTS media_ai_profiles (
    media_id BIGINT PRIMARY KEY
        REFERENCES media_files(id) ON DELETE CASCADE,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    provider VARCHAR(32),
    model VARCHAR(160),
    analysis_version SMALLINT NOT NULL DEFAULT 1,
    analysis JSONB NOT NULL DEFAULT '{}'::JSONB,
    semantic_text TEXT,
    error_message TEXT,
    attempt_count SMALLINT NOT NULL DEFAULT 0,
    analyzed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT media_ai_profiles_status_check
        CHECK (status IN ('pending', 'processing', 'ready', 'error', 'skipped')),
    CONSTRAINT media_ai_profiles_attempt_count_check
        CHECK (attempt_count BETWEEN 0 AND 20)
);

CREATE INDEX IF NOT EXISTS idx_media_ai_profiles_status
    ON media_ai_profiles(status, updated_at, media_id);

CREATE INDEX IF NOT EXISTS idx_media_ai_profiles_ready
    ON media_ai_profiles(media_id)
    WHERE status = 'ready';
