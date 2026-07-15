ALTER TABLE character_media
    ADD COLUMN IF NOT EXISTS is_spoiler BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_character_media_spoiler
    ON character_media(character_id, is_spoiler, created_at DESC, media_id DESC);
