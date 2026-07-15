CREATE TABLE IF NOT EXISTS characters (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    normalized_name VARCHAR(64) NOT NULL UNIQUE,
    created_by BIGINT,
    created_in_chat BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS media_files (
    id BIGSERIAL PRIMARY KEY,
    telegram_file_id TEXT NOT NULL,
    telegram_file_unique_id TEXT NOT NULL UNIQUE,
    original_file_name TEXT,
    storage_file_name TEXT NOT NULL UNIQUE,
    media_type VARCHAR(32) NOT NULL,
    mime_type TEXT,
    file_size BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS character_media (
    character_id BIGINT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    media_id BIGINT NOT NULL REFERENCES media_files(id) ON DELETE CASCADE,
    saved_by BIGINT,
    saved_in_chat BIGINT NOT NULL,
    source_chat_id BIGINT NOT NULL,
    source_message_id BIGINT NOT NULL,
    source_thread_id BIGINT,
    command_message_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (character_id, media_id)
);

CREATE INDEX IF NOT EXISTS idx_character_media_character
    ON character_media(character_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_character_media_source
    ON character_media(source_chat_id, source_message_id);
