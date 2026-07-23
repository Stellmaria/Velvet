ALTER TABLE media_rework_items
    ADD COLUMN IF NOT EXISTS workspace_id BIGINT;

UPDATE media_rework_items
SET workspace_id = 1
WHERE workspace_id IS NULL;

ALTER TABLE media_rework_items
    ALTER COLUMN workspace_id SET DEFAULT 1,
    ALTER COLUMN workspace_id SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'media_rework_items_workspace_id_fkey'
    ) THEN
        ALTER TABLE media_rework_items
            ADD CONSTRAINT media_rework_items_workspace_id_fkey
            FOREIGN KEY (workspace_id)
            REFERENCES workspaces(id)
            ON DELETE CASCADE;
    END IF;
END;
$$;

ALTER TABLE media_rework_events
    ADD COLUMN IF NOT EXISTS workspace_id BIGINT;

UPDATE media_rework_events
SET workspace_id = 1
WHERE workspace_id IS NULL;

ALTER TABLE media_rework_events
    ALTER COLUMN workspace_id SET DEFAULT 1,
    ALTER COLUMN workspace_id SET NOT NULL;

ALTER TABLE media_rework_events
    DROP CONSTRAINT IF EXISTS media_rework_events_media_id_fkey;

ALTER TABLE media_rework_items
    DROP CONSTRAINT IF EXISTS media_rework_items_pkey;

ALTER TABLE media_rework_items
    ADD CONSTRAINT media_rework_items_pkey
    PRIMARY KEY (workspace_id, media_id);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'media_rework_events_workspace_media_fkey'
    ) THEN
        ALTER TABLE media_rework_events
            ADD CONSTRAINT media_rework_events_workspace_media_fkey
            FOREIGN KEY (workspace_id, media_id)
            REFERENCES media_rework_items(workspace_id, media_id)
            ON DELETE CASCADE;
    END IF;
END;
$$;

DROP INDEX IF EXISTS idx_media_rework_active_updated;
CREATE INDEX idx_media_rework_active_updated
    ON media_rework_items(
        workspace_id,
        status,
        updated_at DESC,
        media_id DESC
    )
    WHERE status IN ('needs_fix', 'checking', 'ready_for_review');

DROP INDEX IF EXISTS idx_media_rework_events_media_created;
CREATE INDEX idx_media_rework_events_media_created
    ON media_rework_events(
        workspace_id,
        media_id,
        created_at DESC,
        id DESC
    );

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
        WHERE workspace_id = 1
          AND media_id = NEW.media_id
          AND status IN ('needs_fix', 'checking', 'ready_for_review')
        RETURNING media_id INTO changed_media_id;

        IF changed_media_id IS NOT NULL THEN
            INSERT INTO media_rework_events (
                workspace_id,
                media_id,
                action,
                source,
                actor_user_id
            )
            VALUES (
                1,
                NEW.media_id,
                'accepted',
                'admin',
                NEW.decided_by
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
            workspace_id,
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
            1,
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
        ON CONFLICT (workspace_id, media_id) DO UPDATE
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
            workspace_id,
            media_id,
            action,
            source,
            actor_user_id,
            reason,
            payload
        )
        VALUES (
            1,
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
        WHERE workspace_id = 1
          AND media_id = NEW.media_id
          AND status = 'checking'
        RETURNING media_id INTO changed_media_id;

        IF changed_media_id IS NOT NULL THEN
            INSERT INTO media_rework_events (
                workspace_id,
                media_id,
                action,
                source,
                reason,
                payload
            )
            VALUES (
                1,
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
