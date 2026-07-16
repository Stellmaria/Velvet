ALTER TABLE channel_posts
    ADD COLUMN IF NOT EXISTS discussion_root_message_id BIGINT,
    ADD COLUMN IF NOT EXISTS is_discussion_root BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS source_channel_message_id BIGINT;

CREATE INDEX IF NOT EXISTS idx_channel_posts_discussion_root
    ON channel_posts(channel_id, discussion_root_message_id, posted_at)
    WHERE discussion_root_message_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_channel_posts_source_channel_message
    ON channel_posts(channel_id, source_channel_message_id)
    WHERE source_channel_message_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS discussion_threads (
    discussion_chat_id BIGINT NOT NULL
        REFERENCES tracked_channels(chat_id) ON DELETE CASCADE,
    root_message_id BIGINT NOT NULL,
    parent_channel_id BIGINT NOT NULL
        REFERENCES tracked_channels(chat_id) ON DELETE CASCADE,
    channel_message_id BIGINT,
    channel_post_id BIGINT REFERENCES channel_posts(id) ON DELETE SET NULL,
    link_source VARCHAR(32) NOT NULL DEFAULT 'live',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (discussion_chat_id, root_message_id),
    CONSTRAINT discussion_threads_not_self_parent_check
        CHECK (discussion_chat_id <> parent_channel_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_discussion_threads_source_message
    ON discussion_threads(discussion_chat_id, channel_message_id)
    WHERE channel_message_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_discussion_threads_channel_post
    ON discussion_threads(channel_post_id, discussion_chat_id)
    WHERE channel_post_id IS NOT NULL;

-- Best-effort backfill for already imported Telegram Desktop discussions.
-- Automatic forwards normally have a channel/chat sender and become the root
-- of a reply tree. Ordinary unthreaded conversation is deliberately ignored.
WITH roots AS (
    SELECT p.id
    FROM channel_posts AS p
    JOIN tracked_channels AS discussion
      ON discussion.chat_id = p.channel_id
     AND discussion.source_kind = 'discussion'
    WHERE p.reply_to_message_id IS NULL
      AND (
          p.sender_id LIKE 'channel%'
          OR p.sender_id LIKE 'chat%'
          OR EXISTS (
              SELECT 1
              FROM tracked_channels AS parent
              WHERE parent.chat_id = discussion.parent_channel_id
                AND parent.title IS NOT NULL
                AND p.sender_name IS NOT NULL
                AND LOWER(parent.title) = LOWER(p.sender_name)
          )
      )
      AND EXISTS (
          SELECT 1
          FROM channel_posts AS child
          WHERE child.channel_id = p.channel_id
            AND child.reply_to_message_id = p.message_id
      )
)
UPDATE channel_posts AS p
SET is_discussion_root = TRUE,
    discussion_root_message_id = p.message_id
FROM roots
WHERE p.id = roots.id;

WITH RECURSIVE reply_tree AS (
    SELECT channel_id, message_id, message_id AS root_message_id
    FROM channel_posts
    WHERE is_discussion_root = TRUE

    UNION

    SELECT child.channel_id, child.message_id, parent.root_message_id
    FROM channel_posts AS child
    JOIN reply_tree AS parent
      ON parent.channel_id = child.channel_id
     AND parent.message_id = child.reply_to_message_id
)
UPDATE channel_posts AS target
SET discussion_root_message_id = reply_tree.root_message_id
FROM reply_tree
WHERE target.channel_id = reply_tree.channel_id
  AND target.message_id = reply_tree.message_id
  AND target.discussion_root_message_id IS DISTINCT FROM reply_tree.root_message_id;

INSERT INTO discussion_threads (
    discussion_chat_id,
    root_message_id,
    parent_channel_id,
    channel_message_id,
    channel_post_id,
    link_source,
    updated_at
)
SELECT
    root.channel_id,
    root.message_id,
    discussion.parent_channel_id,
    matched.message_id,
    matched.id,
    'backfill_exact_text',
    NOW()
FROM channel_posts AS root
JOIN tracked_channels AS discussion
  ON discussion.chat_id = root.channel_id
 AND discussion.source_kind = 'discussion'
 AND discussion.parent_channel_id IS NOT NULL
JOIN LATERAL (
    SELECT candidate.id, candidate.message_id
    FROM channel_posts AS candidate
    WHERE candidate.channel_id = discussion.parent_channel_id
      AND NULLIF(BTRIM(root.text_content), '') IS NOT NULL
      AND candidate.text_content = root.text_content
      AND ABS(EXTRACT(EPOCH FROM (candidate.posted_at - root.posted_at))) <= 3600
    ORDER BY ABS(EXTRACT(EPOCH FROM (candidate.posted_at - root.posted_at))),
             candidate.id
    LIMIT 1
) AS matched ON TRUE
WHERE root.is_discussion_root = TRUE
ON CONFLICT (discussion_chat_id, root_message_id) DO UPDATE
SET parent_channel_id = EXCLUDED.parent_channel_id,
    channel_message_id = COALESCE(
        discussion_threads.channel_message_id,
        EXCLUDED.channel_message_id
    ),
    channel_post_id = COALESCE(
        discussion_threads.channel_post_id,
        EXCLUDED.channel_post_id
    ),
    link_source = CASE
        WHEN discussion_threads.channel_post_id IS NULL
            THEN EXCLUDED.link_source
        ELSE discussion_threads.link_source
    END,
    updated_at = NOW();

CREATE TABLE IF NOT EXISTS backup_settings (
    id SMALLINT PRIMARY KEY DEFAULT 1,
    daily_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    daily_hour SMALLINT NOT NULL DEFAULT 3,
    weekly_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    weekly_weekday SMALLINT NOT NULL DEFAULT 6,
    weekly_hour SMALLINT NOT NULL DEFAULT 4,
    retention_count INTEGER NOT NULL DEFAULT 14,
    timezone TEXT NOT NULL DEFAULT 'Europe/Berlin',
    updated_by BIGINT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT backup_settings_singleton_check CHECK (id = 1),
    CONSTRAINT backup_settings_daily_hour_check CHECK (daily_hour BETWEEN 0 AND 23),
    CONSTRAINT backup_settings_weekly_hour_check CHECK (weekly_hour BETWEEN 0 AND 23),
    CONSTRAINT backup_settings_weekday_check CHECK (weekly_weekday BETWEEN 0 AND 6),
    CONSTRAINT backup_settings_retention_check CHECK (retention_count BETWEEN 3 AND 100)
);

INSERT INTO backup_settings (id)
VALUES (1)
ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS backup_runs (
    id BIGSERIAL PRIMARY KEY,
    backup_kind VARCHAR(24) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'running',
    file_name TEXT,
    file_path TEXT,
    size_bytes BIGINT,
    sha256 CHAR(64),
    schema_version TEXT,
    expected_tables JSONB NOT NULL DEFAULT '[]'::JSONB,
    discovered_tables JSONB NOT NULL DEFAULT '[]'::JSONB,
    validation JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_by BIGINT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    error_message TEXT,
    CONSTRAINT backup_runs_kind_check
        CHECK (backup_kind IN ('manual', 'daily', 'weekly', 'pre_migration')),
    CONSTRAINT backup_runs_status_check
        CHECK (status IN ('running', 'valid', 'invalid', 'failed'))
);

CREATE INDEX IF NOT EXISTS idx_backup_runs_started
    ON backup_runs(started_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_backup_runs_status
    ON backup_runs(status, started_at DESC);
