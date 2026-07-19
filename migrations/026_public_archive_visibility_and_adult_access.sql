ALTER TABLE character_media
    ADD COLUMN IF NOT EXISTS is_public BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS requires_adult_channel BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_character_media_public_browse
    ON character_media(character_id, created_at DESC, media_id DESC)
    WHERE is_public = TRUE;

CREATE INDEX IF NOT EXISTS idx_character_media_adult_access
    ON character_media(character_id, requires_adult_channel, created_at DESC, media_id DESC)
    WHERE is_public = TRUE;
