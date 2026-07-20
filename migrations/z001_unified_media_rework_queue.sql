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
    CASE WHEN q.decision = 'fix_required' THEN 'admin' ELSE 'qwen' END,
    COALESCE(q.report ->> 'summary_ru', 'Qwen рекомендовал доработку.'),
    q.verdict,
    q.quality_score,
    COALESCE(q.analyzed_at, NOW()),
    NOW()
FROM media_ai_quality_checks AS q
WHERE q.status = 'ready'
  AND q.decision IS DISTINCT FROM 'accepted'
  AND (
        q.decision = 'fix_required'
        OR q.verdict = 'critical'
        OR COALESCE(q.quality_score, 100) < 70
      )
ON CONFLICT (media_id) DO NOTHING;

CREATE OR REPLACE FUNCTION sync_media_rework_from_quality()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    desired_source VARCHAR(16);
    desired_reason TEXT;
    changed_media_id BIGINT;
BEGIN
    IF NEW.decision = 'accepted' THEN
        UPDATE media_rework_items
        SET status = 'accepted',
            last_action_by = NEW.decided_by,
            resolved_at = NOW(),
            updated_at = NOW()
        WHERE media_id = NEW.media_id
          AND status IN ('needs_fix', 'checking', 'ready_for_review')
        RETURNING media_id INTO changed_media_id;

        IF changed_media_id IS NOT NULL THEN
            INSERT INTO media_rework_events (
                media_id, action, source, actor_user_id
            )
            VALUES (
                NEW.media_id, 'accepted', 'admin', NEW.decided_by
            );
        END IF;
        RETURN NEW;
    END IF;

    IF NEW.status = 'ready'
       AND (
            NEW.decision = 'fix_required'
            OR NEW.verdict = 'critical'
            OR COALESCE(NEW.quality_score, 100) < 70
       ) THEN
        desired_source := CASE
            WHEN NEW.decision = 'fix_required' THEN 'admin'
            ELSE 'qwen'
        END;
        desired_reason := COALESCE(
            NEW.report ->> 'summary_ru',
            CASE
                WHEN NEW.decision = 'fix_required'
                    THEN 'Администратор отправил работу на доработку.'
                ELSE 'Qwen рекомендовал доработку.'
            END
        );

        INSERT INTO media_rework_items AS rework (
            media_id,
            status,
            source,
            reason,
            qwen_verdict,
            qwen_score,
            requested_by,
            last_action_by,
            updated_at
        )
        VALUES (
            NEW.media_id,
            'needs_fix',
            desired_source,
            desired_reason,
            NEW.verdict,
            NEW.quality_score,
            NEW.decided_by,
            NEW.decided_by,
            NOW()
        )
        ON CONFLICT (media_id) DO UPDATE
        SET status = 'needs_fix',
            source = CASE
                WHEN rework.source = EXCLUDED.source THEN rework.source
                ELSE 'mixed'
            END,
            reason = EXCLUDED.reason,
            qwen_verdict = EXCLUDED.qwen_verdict,
            qwen_score = EXCLUDED.qwen_score,
            requested_by = COALESCE(EXCLUDED.requested_by, rework.requested_by),
            last_action_by = COALESCE(EXCLUDED.last_action_by, rework.last_action_by),
            resolved_at = NULL,
            updated_at = NOW();

        INSERT INTO media_rework_events (
            media_id,
            action,
            source,
            actor_user_id,
            reason,
            payload
        )
        VALUES (
            NEW.media_id,
            CASE
                WHEN NEW.decision = 'fix_required'
                    THEN 'admin_flagged'
                ELSE 'qwen_flagged'
            END,
            desired_source,
            NEW.decided_by,
            desired_reason,
            NEW.report
        );
        RETURN NEW;
    END IF;

    IF NEW.status = 'ready' THEN
        UPDATE media_rework_items
        SET status = 'ready_for_review',
            reason = COALESCE(
                NEW.report ->> 'summary_ru',
                'Повторная проверка Qwen завершена.'
            ),
            qwen_verdict = NEW.verdict,
            qwen_score = NEW.quality_score,
            updated_at = NOW()
        WHERE media_id = NEW.media_id
          AND status = 'checking'
        RETURNING media_id INTO changed_media_id;

        IF changed_media_id IS NOT NULL THEN
            INSERT INTO media_rework_events (
                media_id, action, source, reason, payload
            )
            VALUES (
                NEW.media_id,
                'recheck_ready',
                'system',
                COALESCE(
                    NEW.report ->> 'summary_ru',
                    'Повторная проверка Qwen завершена.'
                ),
                NEW.report
            );
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_media_rework_from_quality
    ON media_ai_quality_checks;
CREATE TRIGGER trg_media_rework_from_quality
AFTER INSERT OR UPDATE
ON media_ai_quality_checks
FOR EACH ROW
EXECUTE FUNCTION sync_media_rework_from_quality();
