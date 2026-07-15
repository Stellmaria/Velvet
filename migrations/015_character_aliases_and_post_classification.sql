CREATE TABLE IF NOT EXISTS character_aliases (
    id BIGSERIAL PRIMARY KEY,
    character_id BIGINT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    normalized_alias TEXT NOT NULL,
    source VARCHAR(16) NOT NULL DEFAULT 'manual',
    created_by BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT character_aliases_source_check
        CHECK (source IN ('name', 'manual', 'import')),
    CONSTRAINT character_aliases_normalized_unique UNIQUE (normalized_alias),
    CONSTRAINT character_aliases_character_alias_unique
        UNIQUE (character_id, normalized_alias)
);

CREATE INDEX IF NOT EXISTS idx_character_aliases_character
    ON character_aliases(character_id, alias);

INSERT INTO character_aliases (
    character_id,
    alias,
    normalized_alias,
    source
)
SELECT
    c.id,
    c.name,
    LOWER(REGEXP_REPLACE(c.name, '[^[:alnum:]]+', '', 'g')),
    'name'
FROM characters AS c
WHERE REGEXP_REPLACE(c.name, '[^[:alnum:]]+', '', 'g') <> ''
ON CONFLICT (normalized_alias) DO NOTHING;

ALTER TABLE channel_posts
    ADD COLUMN IF NOT EXISTS post_type VARCHAR(24) NOT NULL DEFAULT 'unknown',
    ADD COLUMN IF NOT EXISTS post_type_confidence SMALLINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS post_type_source VARCHAR(16) NOT NULL DEFAULT 'automatic';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'channel_posts_post_type_check'
    ) THEN
        ALTER TABLE channel_posts
            ADD CONSTRAINT channel_posts_post_type_check
            CHECK (
                post_type IN (
                    'prompt',
                    'art',
                    'announcement',
                    'giveaway',
                    'collaboration',
                    'update',
                    'service',
                    'unknown'
                )
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'channel_posts_post_type_confidence_check'
    ) THEN
        ALTER TABLE channel_posts
            ADD CONSTRAINT channel_posts_post_type_confidence_check
            CHECK (post_type_confidence BETWEEN 0 AND 100);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'channel_posts_post_type_source_check'
    ) THEN
        ALTER TABLE channel_posts
            ADD CONSTRAINT channel_posts_post_type_source_check
            CHECK (post_type_source IN ('automatic', 'manual'));
    END IF;
END;
$$;

UPDATE channel_posts
SET post_type = 'prompt',
    post_type_confidence = GREATEST(post_type_confidence, 95),
    post_type_source = 'automatic'
WHERE is_prompt = TRUE
  AND post_type_source <> 'manual';

CREATE INDEX IF NOT EXISTS idx_channel_posts_type_date
    ON channel_posts(channel_id, post_type, posted_at DESC);
