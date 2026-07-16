CREATE TABLE IF NOT EXISTS media_sets (
    id BIGSERIAL PRIMARY KEY,
    title VARCHAR(160) NOT NULL,
    prompt_post_url TEXT,
    created_by BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT media_sets_title_check CHECK (BTRIM(title) <> '')
);

ALTER TABLE media_files
    ADD COLUMN IF NOT EXISTS media_set_id BIGINT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'media_files_media_set_id_fkey'
    ) THEN
        ALTER TABLE media_files
            ADD CONSTRAINT media_files_media_set_id_fkey
            FOREIGN KEY (media_set_id)
            REFERENCES media_sets(id)
            ON DELETE SET NULL;
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_media_files_media_set
    ON media_files(media_set_id, id)
    WHERE media_set_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS media_set_candidates (
    id BIGSERIAL PRIMARY KEY,
    candidate_key TEXT NOT NULL UNIQUE,
    suggested_title VARCHAR(160) NOT NULL,
    reason TEXT NOT NULL,
    score SMALLINT NOT NULL,
    prompt_post_url TEXT,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    decided_by BIGINT,
    decided_at TIMESTAMPTZ,
    created_set_id BIGINT REFERENCES media_sets(id) ON DELETE SET NULL,
    CONSTRAINT media_set_candidates_score_check CHECK (score BETWEEN 0 AND 100),
    CONSTRAINT media_set_candidates_status_check
        CHECK (status IN ('pending', 'accepted', 'ignored'))
);

CREATE INDEX IF NOT EXISTS idx_media_set_candidates_status
    ON media_set_candidates(status, score DESC, id);

CREATE TABLE IF NOT EXISTS media_set_candidate_items (
    candidate_id BIGINT NOT NULL
        REFERENCES media_set_candidates(id) ON DELETE CASCADE,
    media_id BIGINT NOT NULL
        REFERENCES media_files(id) ON DELETE CASCADE,
    selected BOOLEAN NOT NULL DEFAULT TRUE,
    context_score SMALLINT NOT NULL DEFAULT 0,
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (candidate_id, media_id),
    CONSTRAINT media_set_candidate_items_score_check
        CHECK (context_score BETWEEN 0 AND 100)
);

CREATE INDEX IF NOT EXISTS idx_media_set_candidate_items_media
    ON media_set_candidate_items(media_id, candidate_id);

CREATE OR REPLACE FUNCTION sync_media_set_prompt_from_character_media()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    target_set_id BIGINT;
BEGIN
    IF pg_trigger_depth() > 1 THEN
        RETURN NEW;
    END IF;

    SELECT media_set_id
    INTO target_set_id
    FROM media_files
    WHERE id = NEW.media_id;

    IF target_set_id IS NULL THEN
        RETURN NEW;
    END IF;

    UPDATE media_sets
    SET prompt_post_url = NEW.prompt_post_url,
        updated_at = NOW()
    WHERE id = target_set_id
      AND prompt_post_url IS DISTINCT FROM NEW.prompt_post_url;

    UPDATE character_media AS cm
    SET prompt_post_url = NEW.prompt_post_url
    FROM media_files AS mf
    WHERE mf.id = cm.media_id
      AND mf.media_set_id = target_set_id
      AND cm.prompt_post_url IS DISTINCT FROM NEW.prompt_post_url;

    RETURN NEW;
END
$$;

DROP TRIGGER IF EXISTS trg_character_media_sync_set_prompt ON character_media;
CREATE TRIGGER trg_character_media_sync_set_prompt
AFTER UPDATE OF prompt_post_url ON character_media
FOR EACH ROW
EXECUTE FUNCTION sync_media_set_prompt_from_character_media();
