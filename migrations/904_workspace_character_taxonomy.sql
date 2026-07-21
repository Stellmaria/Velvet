CREATE TABLE IF NOT EXISTS workspace_character_story_links (
    workspace_id BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    character_id BIGINT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    story_id BIGINT NOT NULL REFERENCES workspace_stories(id) ON DELETE CASCADE,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    assigned_by_user_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (character_id, story_id)
);

CREATE INDEX IF NOT EXISTS idx_workspace_character_story_links_workspace
    ON workspace_character_story_links (workspace_id, character_id, is_primary, story_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_workspace_character_story_primary
    ON workspace_character_story_links (character_id)
    WHERE is_primary;
