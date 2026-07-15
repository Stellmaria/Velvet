ALTER TABLE characters
    ADD COLUMN IF NOT EXISTS archive_chat_id BIGINT,
    ADD COLUMN IF NOT EXISTS archive_thread_id BIGINT,
    ADD COLUMN IF NOT EXISTS archive_topic_url TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS uq_characters_archive_topic
    ON characters(archive_chat_id, archive_thread_id)
    WHERE archive_chat_id IS NOT NULL AND archive_thread_id IS NOT NULL;

ALTER TABLE character_media
    ALTER COLUMN command_message_id DROP NOT NULL;

ALTER TABLE character_media
    ADD COLUMN IF NOT EXISTS archive_message_id BIGINT;

CREATE INDEX IF NOT EXISTS idx_character_media_archive_message
    ON character_media(character_id, archive_message_id)
    WHERE archive_message_id IS NOT NULL;
