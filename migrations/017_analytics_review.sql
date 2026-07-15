CREATE TABLE IF NOT EXISTS analytics_review_items (
    id BIGSERIAL PRIMARY KEY,
    channel_id BIGINT NOT NULL,
    item_kind VARCHAR(16) NOT NULL,
    item_key TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT analytics_review_items_kind_check
        CHECK (item_kind IN ('hashtag', 'publication')),
    CONSTRAINT analytics_review_items_unique
        UNIQUE (channel_id, item_kind, item_key)
);

CREATE TABLE IF NOT EXISTS post_classification_changes (
    id BIGSERIAL PRIMARY KEY,
    channel_id BIGINT NOT NULL,
    publication_key TEXT NOT NULL,
    previous_type VARCHAR(24) NOT NULL,
    new_type VARCHAR(24) NOT NULL,
    previous_confidence SMALLINT NOT NULL,
    new_confidence SMALLINT NOT NULL,
    previous_source VARCHAR(16) NOT NULL,
    new_source VARCHAR(16) NOT NULL,
    changed_by BIGINT,
    reason TEXT,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_analytics_review_items_lookup
    ON analytics_review_items(channel_id, item_kind, id);

CREATE INDEX IF NOT EXISTS idx_post_classification_changes_publication
    ON post_classification_changes(channel_id, publication_key, changed_at DESC);

CREATE INDEX IF NOT EXISTS idx_channel_posts_review_queue
    ON channel_posts(channel_id, post_type_source, post_type_confidence, posted_at DESC);
