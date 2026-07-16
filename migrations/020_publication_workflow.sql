CREATE TABLE IF NOT EXISTS publication_inbox_items (
    id BIGSERIAL PRIMARY KEY,
    owner_id BIGINT NOT NULL,
    source_chat_id BIGINT NOT NULL,
    source_message_id BIGINT NOT NULL,
    media_group_id TEXT,
    text_content TEXT NOT NULL DEFAULT '',
    telegram_file_id TEXT,
    telegram_file_unique_id TEXT,
    media_type VARCHAR(24) NOT NULL DEFAULT 'text',
    mime_type TEXT,
    file_name TEXT,
    file_size BIGINT,
    has_spoiler BOOLEAN NOT NULL DEFAULT FALSE,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT publication_inbox_owner_message_unique
        UNIQUE (owner_id, source_chat_id, source_message_id)
);

CREATE TABLE IF NOT EXISTS publication_drafts (
    id BIGSERIAL PRIMARY KEY,
    owner_id BIGINT NOT NULL,
    target_chat_id BIGINT NOT NULL,
    source_chat_id BIGINT,
    source_message_id BIGINT,
    source_media_group_id TEXT,
    text_content TEXT NOT NULL DEFAULT '',
    status VARCHAR(24) NOT NULL DEFAULT 'draft',
    post_type VARCHAR(24) NOT NULL DEFAULT 'unknown',
    has_spoiler BOOLEAN NOT NULL DEFAULT FALSE,
    content_hash CHAR(64) NOT NULL,
    validation_status VARCHAR(16) NOT NULL DEFAULT 'pending',
    validation_error_count INTEGER NOT NULL DEFAULT 0,
    validation_warning_count INTEGER NOT NULL DEFAULT 0,
    validation_report JSONB NOT NULL DEFAULT '[]'::JSONB,
    scheduled_at TIMESTAMPTZ,
    published_at TIMESTAMPTZ,
    published_message_ids BIGINT[] NOT NULL DEFAULT '{}',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT publication_drafts_status_check CHECK (
        status IN (
            'draft', 'checked', 'scheduled', 'publishing',
            'published', 'error', 'cancelled'
        )
    ),
    CONSTRAINT publication_drafts_validation_check CHECK (
        validation_status IN ('pending', 'passed', 'warning', 'failed')
    )
);

CREATE TABLE IF NOT EXISTS publication_draft_items (
    id BIGSERIAL PRIMARY KEY,
    draft_id BIGINT NOT NULL REFERENCES publication_drafts(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    telegram_file_id TEXT NOT NULL,
    telegram_file_unique_id TEXT,
    media_type VARCHAR(24) NOT NULL,
    mime_type TEXT,
    file_name TEXT,
    file_size BIGINT,
    source_message_id BIGINT,
    has_spoiler BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT publication_draft_item_position_unique UNIQUE (draft_id, position)
);

CREATE TABLE IF NOT EXISTS publication_events (
    id BIGSERIAL PRIMARY KEY,
    draft_id BIGINT NOT NULL REFERENCES publication_drafts(id) ON DELETE CASCADE,
    event_type VARCHAR(32) NOT NULL,
    actor_id BIGINT,
    details JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_publication_inbox_group
    ON publication_inbox_items(owner_id, source_chat_id, media_group_id, received_at);

CREATE INDEX IF NOT EXISTS idx_publication_drafts_owner_status
    ON publication_drafts(owner_id, status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_publication_drafts_schedule
    ON publication_drafts(status, scheduled_at)
    WHERE status = 'scheduled';

CREATE INDEX IF NOT EXISTS idx_publication_drafts_hash
    ON publication_drafts(target_chat_id, content_hash, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_publication_events_draft
    ON publication_events(draft_id, created_at DESC);
