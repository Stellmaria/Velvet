CREATE TABLE IF NOT EXISTS media_ai_quality_checks (
    media_id BIGINT PRIMARY KEY REFERENCES media_files(id) ON DELETE CASCADE,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    provider VARCHAR(64),
    model VARCHAR(160),
    analysis_version SMALLINT NOT NULL DEFAULT 1,
    attempt_count SMALLINT NOT NULL DEFAULT 0,
    verdict VARCHAR(16),
    quality_score SMALLINT,
    confidence SMALLINT,
    report JSONB,
    decision VARCHAR(24),
    decided_by BIGINT,
    decided_at TIMESTAMPTZ,
    error_message TEXT,
    analyzed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT media_ai_quality_status_check CHECK (
        status IN ('pending', 'processing', 'ready', 'error', 'skipped')
    ),
    CONSTRAINT media_ai_quality_verdict_check CHECK (
        verdict IS NULL OR verdict IN ('ready', 'review', 'critical')
    ),
    CONSTRAINT media_ai_quality_decision_check CHECK (
        decision IS NULL OR decision IN ('accepted', 'fix_required')
    ),
    CONSTRAINT media_ai_quality_score_check CHECK (
        quality_score IS NULL OR quality_score BETWEEN 0 AND 100
    ),
    CONSTRAINT media_ai_quality_confidence_check CHECK (
        confidence IS NULL OR confidence BETWEEN 0 AND 100
    )
);

CREATE INDEX IF NOT EXISTS idx_media_ai_quality_status_updated
    ON media_ai_quality_checks(status, updated_at, media_id);

CREATE INDEX IF NOT EXISTS idx_media_ai_quality_review_queue
    ON media_ai_quality_checks(decision, verdict, analyzed_at DESC)
    WHERE status = 'ready';
