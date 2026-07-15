CREATE TABLE IF NOT EXISTS tracked_channels (
    chat_id BIGINT PRIMARY KEY,
    title TEXT,
    username TEXT,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_post_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS channel_posts (
    id BIGSERIAL PRIMARY KEY,
    channel_id BIGINT NOT NULL REFERENCES tracked_channels(chat_id) ON DELETE CASCADE,
    message_id BIGINT NOT NULL,
    publication_key TEXT NOT NULL,
    posted_at TIMESTAMPTZ NOT NULL,
    edited_at TIMESTAMPTZ,
    author_signature TEXT,
    text_content TEXT NOT NULL DEFAULT '',
    text_length INTEGER NOT NULL DEFAULT 0,
    media_type VARCHAR(24) NOT NULL DEFAULT 'text',
    media_group_id TEXT,
    has_spoiler BOOLEAN NOT NULL DEFAULT FALSE,
    view_count INTEGER,
    forward_count INTEGER,
    is_prompt BOOLEAN NOT NULL DEFAULT FALSE,
    prompt_score INTEGER NOT NULL DEFAULT 0,
    has_important_section BOOLEAN NOT NULL DEFAULT FALSE,
    has_strict_section BOOLEAN NOT NULL DEFAULT FALSE,
    has_negative_section BOOLEAN NOT NULL DEFAULT FALSE,
    has_technical_section BOOLEAN NOT NULL DEFAULT FALSE,
    has_palette BOOLEAN NOT NULL DEFAULT FALSE,
    message_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT channel_posts_channel_message_unique UNIQUE (channel_id, message_id)
);

CREATE TABLE IF NOT EXISTS channel_post_hashtags (
    post_id BIGINT NOT NULL REFERENCES channel_posts(id) ON DELETE CASCADE,
    hashtag TEXT NOT NULL,
    normalized_hashtag TEXT NOT NULL,
    character_id BIGINT REFERENCES characters(id) ON DELETE SET NULL,
    is_character BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (post_id, normalized_hashtag)
);

CREATE TABLE IF NOT EXISTS channel_post_links (
    post_id BIGINT NOT NULL REFERENCES channel_posts(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    domain TEXT NOT NULL,
    is_telegram BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (post_id, url)
);

CREATE INDEX IF NOT EXISTS idx_channel_posts_channel_date
    ON channel_posts(channel_id, posted_at DESC, message_id DESC);

CREATE INDEX IF NOT EXISTS idx_channel_posts_publication
    ON channel_posts(channel_id, publication_key);

CREATE INDEX IF NOT EXISTS idx_channel_posts_prompt_date
    ON channel_posts(channel_id, is_prompt, posted_at DESC);

CREATE INDEX IF NOT EXISTS idx_channel_hashtags_normalized
    ON channel_post_hashtags(normalized_hashtag, post_id);

CREATE INDEX IF NOT EXISTS idx_channel_hashtags_character
    ON channel_post_hashtags(character_id, post_id)
    WHERE character_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_channel_links_domain
    ON channel_post_links(domain, post_id);

INSERT INTO tracked_channels (chat_id, enabled)
VALUES (-1003802812639, TRUE)
ON CONFLICT (chat_id) DO UPDATE
SET enabled = TRUE,
    updated_at = NOW();
