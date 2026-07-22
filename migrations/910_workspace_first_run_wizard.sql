CREATE TABLE IF NOT EXISTS workspace_onboarding (
    workspace_id BIGINT PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,
    status VARCHAR(24) NOT NULL DEFAULT 'not_started' CHECK (
        status IN ('not_started', 'in_progress', 'completed')
    ),
    current_step VARCHAR(32) NOT NULL DEFAULT 'intro',
    modules_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
    guide_viewed BOOLEAN NOT NULL DEFAULT FALSE,
    started_by_user_id BIGINT,
    completed_by_user_id BIGINT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS workspace_destinations (
    workspace_id BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    destination_key VARCHAR(32) NOT NULL CHECK (
        destination_key IN (
            'characters',
            'media',
            'references',
            'public',
            'publications',
            'discussion',
            'analytics',
            'logs'
        )
    ),
    chat_id BIGINT NOT NULL,
    message_thread_id BIGINT,
    chat_type VARCHAR(32) NOT NULL,
    chat_title VARCHAR(255),
    topic_title VARCHAR(255),
    url TEXT,
    bot_status VARCHAR(32) NOT NULL,
    can_post BOOLEAN NOT NULL DEFAULT FALSE,
    can_manage_topics BOOLEAN NOT NULL DEFAULT FALSE,
    configured_by_user_id BIGINT NOT NULL,
    verified_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (workspace_id, destination_key)
);

CREATE INDEX IF NOT EXISTS idx_workspace_destinations_chat
    ON workspace_destinations (chat_id, message_thread_id, workspace_id);

CREATE OR REPLACE FUNCTION enforce_workspace_destination_chat_ownership()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(NEW.chat_id);

    IF EXISTS (
        SELECT 1
        FROM workspace_destinations AS destination
        WHERE destination.chat_id = NEW.chat_id
          AND destination.workspace_id <> NEW.workspace_id
    ) OR EXISTS (
        SELECT 1
        FROM workspace_channels AS channel
        WHERE channel.chat_id = NEW.chat_id
          AND channel.workspace_id <> NEW.workspace_id
    ) THEN
        RAISE EXCEPTION 'Этот Telegram-чат уже подключён к другому пространству.'
            USING ERRCODE = '23505';
    END IF;

    RETURN NEW;
END
$$;

DROP TRIGGER IF EXISTS trg_workspace_destination_chat_ownership
    ON workspace_destinations;

CREATE TRIGGER trg_workspace_destination_chat_ownership
BEFORE INSERT OR UPDATE OF chat_id, workspace_id
ON workspace_destinations
FOR EACH ROW
EXECUTE FUNCTION enforce_workspace_destination_chat_ownership();

INSERT INTO workspace_onboarding (
    workspace_id,
    status,
    current_step,
    modules_confirmed,
    guide_viewed,
    started_at,
    completed_at
)
SELECT
    w.id,
    CASE WHEN w.is_system THEN 'completed' ELSE 'not_started' END,
    CASE WHEN w.is_system THEN 'complete' ELSE 'intro' END,
    w.is_system,
    w.is_system,
    CASE WHEN w.is_system THEN NOW() ELSE NULL END,
    CASE WHEN w.is_system THEN NOW() ELSE NULL END
FROM workspaces AS w
ON CONFLICT (workspace_id) DO NOTHING;
