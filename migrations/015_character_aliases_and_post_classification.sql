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

CREATE OR REPLACE FUNCTION resolve_character_alias_for_hashtag()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    resolved_character_id BIGINT;
    compact_tag TEXT;
BEGIN
    IF NEW.character_id IS NOT NULL THEN
        NEW.is_character := TRUE;
        RETURN NEW;
    END IF;

    compact_tag := LOWER(
        REGEXP_REPLACE(NEW.normalized_hashtag, '[^[:alnum:]]+', '', 'g')
    );
    SELECT character_id
    INTO resolved_character_id
    FROM character_aliases
    WHERE normalized_alias = compact_tag
    LIMIT 1;

    IF resolved_character_id IS NOT NULL THEN
        NEW.character_id := resolved_character_id;
        NEW.is_character := TRUE;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_resolve_character_alias_for_hashtag
    ON channel_post_hashtags;

CREATE TRIGGER trg_resolve_character_alias_for_hashtag
BEFORE INSERT OR UPDATE OF normalized_hashtag, character_id
ON channel_post_hashtags
FOR EACH ROW
EXECUTE FUNCTION resolve_character_alias_for_hashtag();

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

CREATE OR REPLACE FUNCTION classify_channel_post_text()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    body TEXT := LOWER(COALESCE(NEW.text_content, ''));
BEGIN
    IF NEW.post_type_source = 'manual' THEN
        RETURN NEW;
    END IF;

    NEW.post_type_source := 'automatic';
    IF NEW.is_prompt THEN
        NEW.post_type := 'prompt';
        NEW.post_type_confidence := 98;
    ELSIF body ~ '(условия участия|победител|призовой фонд|розыгрыш|конкурс)' THEN
        NEW.post_type := 'giveaway';
        NEW.post_type_confidence := 84;
    ELSIF body ~ '(анонс на|сегодня выходит|завтра выходит|анонс)' THEN
        NEW.post_type := 'announcement';
        NEW.post_type_confidence := 82;
    ELSIF body ~ '(совместная работа|в коллаборации|совместно с|совместка)' THEN
        NEW.post_type := 'collaboration';
        NEW.post_type_confidence := 82;
    ELSIF body ~ '(обновление канала|новая функция|добавили возможность|обновление)' THEN
        NEW.post_type := 'update';
        NEW.post_type_confidence := 78;
    ELSIF body ~ '(правила канала|навигация по каналу|важная информация)' THEN
        NEW.post_type := 'service';
        NEW.post_type_confidence := 78;
    ELSIF NEW.media_type <> 'text' THEN
        NEW.post_type := 'art';
        NEW.post_type_confidence := 62;
    ELSE
        NEW.post_type := 'unknown';
        NEW.post_type_confidence := 20;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_classify_channel_post_text ON channel_posts;

CREATE TRIGGER trg_classify_channel_post_text
BEFORE INSERT OR UPDATE OF text_content, media_type, is_prompt
ON channel_posts
FOR EACH ROW
EXECUTE FUNCTION classify_channel_post_text();

CREATE OR REPLACE FUNCTION classify_channel_post_hashtag()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    tag TEXT := LOWER(NEW.normalized_hashtag);
    detected_type VARCHAR(24);
    detected_confidence SMALLINT;
BEGIN
    IF tag IN ('промт', 'prompt') THEN
        detected_type := 'prompt'; detected_confidence := 97;
    ELSIF tag IN ('розыгрыш', 'конкурс', 'giveaway') THEN
        detected_type := 'giveaway'; detected_confidence := 98;
    ELSIF tag IN ('анонс', 'announcement') THEN
        detected_type := 'announcement'; detected_confidence := 98;
    ELSIF tag IN ('совместка', 'коллаб', 'collab', 'collaboration') THEN
        detected_type := 'collaboration'; detected_confidence := 98;
    ELSIF tag IN ('обновление', 'update', 'релиз') THEN
        detected_type := 'update'; detected_confidence := 96;
    ELSIF tag IN ('служебный', 'навигация', 'правила', 'информация') THEN
        detected_type := 'service'; detected_confidence := 94;
    ELSIF tag IN (
        'арт', 'art', 'одиночный', 'парный', 'мужской', 'женский',
        'мж', 'мм', 'жж', 'мжм'
    ) THEN
        detected_type := 'art'; detected_confidence := 90;
    ELSE
        RETURN NEW;
    END IF;

    UPDATE channel_posts
    SET post_type = detected_type,
        post_type_confidence = detected_confidence,
        post_type_source = 'automatic'
    WHERE id = NEW.post_id
      AND post_type_source = 'automatic'
      AND post_type_confidence < detected_confidence;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_classify_channel_post_hashtag
    ON channel_post_hashtags;

CREATE TRIGGER trg_classify_channel_post_hashtag
AFTER INSERT OR UPDATE OF normalized_hashtag
ON channel_post_hashtags
FOR EACH ROW
EXECUTE FUNCTION classify_channel_post_hashtag();

UPDATE channel_posts
SET text_content = text_content
WHERE post_type_source <> 'manual';

UPDATE channel_post_hashtags
SET normalized_hashtag = normalized_hashtag,
    character_id = NULL,
    is_character = FALSE;

CREATE INDEX IF NOT EXISTS idx_channel_posts_type_date
    ON channel_posts(channel_id, post_type, posted_at DESC);
