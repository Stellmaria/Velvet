CREATE TABLE IF NOT EXISTS roleplay_sessions (
    chat_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    title VARCHAR(120),
    system_prompt TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (chat_id, user_id)
);

CREATE TABLE IF NOT EXISTS roleplay_messages (
    id BIGSERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    role VARCHAR(16) NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT roleplay_messages_session_fkey
        FOREIGN KEY (chat_id, user_id)
        REFERENCES roleplay_sessions(chat_id, user_id)
        ON DELETE CASCADE,
    CONSTRAINT roleplay_messages_role_check
        CHECK (role IN ('user', 'assistant')),
    CONSTRAINT roleplay_messages_content_check
        CHECK (LENGTH(BTRIM(content)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_roleplay_messages_session_recent
    ON roleplay_messages(chat_id, user_id, id DESC);

CREATE INDEX IF NOT EXISTS idx_roleplay_sessions_enabled
    ON roleplay_sessions(user_id, updated_at DESC)
    WHERE enabled = TRUE;
