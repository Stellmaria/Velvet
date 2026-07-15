CREATE TABLE IF NOT EXISTS character_references (
    id BIGSERIAL PRIMARY KEY,
    character_id BIGINT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    telegram_file_id TEXT NOT NULL,
    telegram_file_unique_id TEXT NOT NULL,
    added_by BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (character_id, telegram_file_unique_id)
);

CREATE INDEX IF NOT EXISTS idx_character_references_character
    ON character_references(character_id, created_at, id);
