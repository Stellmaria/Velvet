CREATE TABLE IF NOT EXISTS media_ai_quality_queue_plans (
    id BIGSERIAL PRIMARY KEY,
    requested_by BIGINT NOT NULL,
    kind VARCHAR(16) NOT NULL,
    requested_limit SMALLINT NOT NULL,
    media_ids BIGINT[] NOT NULL DEFAULT '{}',
    new_count SMALLINT NOT NULL DEFAULT 0,
    legacy_pending_count SMALLINT NOT NULL DEFAULT 0,
    failed_count SMALLINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    started_at TIMESTAMPTZ,
    started_count SMALLINT,
    CONSTRAINT media_ai_quality_queue_plan_kind_check CHECK (
        kind IN ('recent', 'errors')
    ),
    CONSTRAINT media_ai_quality_queue_plan_limit_check CHECK (
        requested_limit BETWEEN 1 AND 100
    ),
    CONSTRAINT media_ai_quality_queue_plan_counts_check CHECK (
        new_count >= 0
        AND legacy_pending_count >= 0
        AND failed_count >= 0
        AND (started_count IS NULL OR started_count >= 0)
    )
);

ALTER TABLE media_ai_quality_checks
    ADD COLUMN IF NOT EXISTS queue_plan_id BIGINT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'media_ai_quality_checks_queue_plan_fk'
    ) THEN
        ALTER TABLE media_ai_quality_checks
            ADD CONSTRAINT media_ai_quality_checks_queue_plan_fk
            FOREIGN KEY (queue_plan_id)
            REFERENCES media_ai_quality_queue_plans(id)
            ON DELETE SET NULL;
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_media_ai_quality_queue_plans_owner_created
    ON media_ai_quality_queue_plans(requested_by, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_media_ai_quality_queue_plan
    ON media_ai_quality_checks(queue_plan_id, status, media_id)
    WHERE queue_plan_id IS NOT NULL;

-- Before this migration there was no explicit plan/start authorization boundary.
-- Any active global quality backlog is therefore legacy by definition. Quarantine
-- it fail-closed; an owner can deliberately adopt exact rows through a new plan.
UPDATE media_ai_quality_checks
SET status = 'skipped',
    error_message = CASE
        WHEN COALESCE(error_message, '') = '' THEN
            'Legacy global quality backlog quarantined by owner-queue migration.'
        ELSE
            LEFT(error_message, 1700)
            || ' | Legacy global quality backlog quarantined by owner-queue migration.'
    END,
    updated_at = NOW()
WHERE queue_plan_id IS NULL
  AND status IN ('pending', 'processing', 'error');
