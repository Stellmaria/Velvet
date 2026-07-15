ALTER TABLE tracked_channels
    ADD COLUMN IF NOT EXISTS source_kind VARCHAR(16) NOT NULL DEFAULT 'channel',
    ADD COLUMN IF NOT EXISTS parent_channel_id BIGINT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'tracked_channels_source_kind_check'
    ) THEN
        ALTER TABLE tracked_channels
            ADD CONSTRAINT tracked_channels_source_kind_check
            CHECK (source_kind IN ('channel', 'discussion'));
    END IF;
END;
$$;

ALTER TABLE channel_posts
    ADD COLUMN IF NOT EXISTS sender_id TEXT,
    ADD COLUMN IF NOT EXISTS sender_name TEXT,
    ADD COLUMN IF NOT EXISTS reply_to_message_id BIGINT,
    ADD COLUMN IF NOT EXISTS topic_id BIGINT,
    ADD COLUMN IF NOT EXISTS reactions_total INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS reaction_breakdown JSONB NOT NULL DEFAULT '{}'::JSONB,
    ADD COLUMN IF NOT EXISTS imported_from_export BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS telegram_export_imports (
    id BIGSERIAL PRIMARY KEY,
    file_sha256 CHAR(64) NOT NULL UNIQUE,
    file_name TEXT NOT NULL,
    source_chat_id BIGINT NOT NULL,
    source_kind VARCHAR(16) NOT NULL,
    parent_channel_id BIGINT,
    imported_by BIGINT,
    total_records INTEGER NOT NULL DEFAULT 0,
    imported_messages INTEGER NOT NULL DEFAULT 0,
    publication_count INTEGER NOT NULL DEFAULT 0,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    CONSTRAINT telegram_export_imports_kind_check
        CHECK (source_kind IN ('channel', 'discussion'))
);

CREATE INDEX IF NOT EXISTS idx_tracked_channels_source_kind
    ON tracked_channels(source_kind, enabled, chat_id);

CREATE INDEX IF NOT EXISTS idx_channel_posts_sender
    ON channel_posts(channel_id, sender_id, posted_at DESC)
    WHERE sender_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_channel_posts_reply
    ON channel_posts(channel_id, reply_to_message_id)
    WHERE reply_to_message_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_channel_posts_imported
    ON channel_posts(channel_id, imported_from_export, posted_at DESC);

UPDATE tracked_channels
SET source_kind = 'channel'
WHERE chat_id = -1003802812639;
