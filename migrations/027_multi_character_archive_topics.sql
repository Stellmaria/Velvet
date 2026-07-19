CREATE TABLE IF NOT EXISTS character_archive_topics (
    character_id BIGINT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    archive_chat_id BIGINT NOT NULL,
    archive_thread_id BIGINT NOT NULL,
    archive_topic_url TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (character_id, archive_chat_id, archive_thread_id)
);

INSERT INTO character_archive_topics (
    character_id,
    archive_chat_id,
    archive_thread_id,
    archive_topic_url
)
SELECT
    id,
    archive_chat_id,
    archive_thread_id,
    archive_topic_url
FROM characters
WHERE archive_chat_id IS NOT NULL
  AND archive_thread_id IS NOT NULL
  AND archive_topic_url IS NOT NULL
ON CONFLICT DO NOTHING;

DROP INDEX IF EXISTS uq_characters_archive_topic;

CREATE INDEX IF NOT EXISTS idx_character_archive_topics_topic
    ON character_archive_topics(archive_chat_id, archive_thread_id, character_id);

CREATE INDEX IF NOT EXISTS idx_character_archive_topics_character
    ON character_archive_topics(character_id, created_at DESC);
