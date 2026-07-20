CREATE TABLE IF NOT EXISTS media_rework_items (
    media_id BIGINT PRIMARY KEY REFERENCES media_files(id) ON DELETE CASCADE,
    status VARCHAR(24) NOT NULL DEFAULT 'needs_fix',
    source VARCHAR(16) NOT NULL DEFAULT 'qwen',
    reason TEXT,
    qwen_verdict VARCHAR(16),
    qwen_score SMALLINT,
    requested_by BIGINT,
    last_action_by BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    CONSTRAINT media_rework_status_check CHECK (
        status IN ('needs_fix', 'checking', 'ready_for_review', 'accepted', 'dismissed')
    ),
    CONSTRAINT media_rework_source_check CHECK (
        source IN ('qwen', 'admin', 'mixed')
    ),
    CONSTRAINT media_rework_qwen_verdict_check CHECK (
        qwen_verdict IS NULL OR qwen_verdict IN ('ready', 'review', 'critical')
    ),
    CONSTRAINT media_rework_qwen_score_check CHECK (
        qwen_score IS NULL OR qwen_score BETWEEN 0 AND 100
    )
);

CREATE INDEX IF NOT EXISTS idx_media_rework_active_updated
    ON media_rework_items(status, updated_at DESC, media_id DESC)
    WHERE status IN ('needs_fix', 'checking', 'ready_for_review');

CREATE TABLE IF NOT EXISTS media_rework_events (
    id BIGSERIAL PRIMARY KEY,
    media_id BIGINT NOT NULL REFERENCES media_rework_items(media_id) ON DELETE CASCADE,
    action VARCHAR(32) NOT NULL,
    source VARCHAR(16) NOT NULL,
    actor_user_id BIGINT,
    reason TEXT,
    payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT media_rework_event_source_check CHECK (
        source IN ('qwen', 'admin', 'system')
    )
);

CREATE INDEX IF NOT EXISTS idx_media_rework_events_media_created
    ON media_rework_events(media_id, created_at DESC, id DESC);

INSERT INTO media_rework_items (
    media_id,
    status,
    source,
    reason,
    qwen_verdict,
    qwen_score,
    created_at,
    updated_at
)
SELECT
    q.media_id,
    'needs_fix',
    'qwen',
    COALESCE(q.report ->> 'summary_ru', 'Qwen рекомендовал доработку.'),
    q.verdict,
    q.quality_score,
    COALESCE(q.analyzed_at, NOW()),
    NOW()
FROM media_ai_quality_checks AS q
WHERE q.status = 'ready'
  AND q.decision IS DISTINCT FROM 'accepted'
  AND (q.verdict = 'critical' OR COALESCE(q.quality_score, 100) < 70)
ON CONFLICT (media_id) DO NOTHING;
