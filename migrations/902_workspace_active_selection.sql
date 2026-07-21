CREATE TABLE IF NOT EXISTS user_workspace_preferences (
    user_id BIGINT PRIMARY KEY,
    active_workspace_id BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_workspace_preferences_workspace
    ON user_workspace_preferences (active_workspace_id, user_id);
