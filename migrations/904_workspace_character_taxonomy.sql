CREATE UNIQUE INDEX IF NOT EXISTS uq_characters_workspace_id_id
    ON characters (workspace_id, id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_workspace_stories_workspace_id_id
    ON workspace_stories (workspace_id, id);

ALTER TABLE characters
    DROP CONSTRAINT IF EXISTS characters_category_check,
    DROP CONSTRAINT IF EXISTS characters_universe_check,
    DROP CONSTRAINT IF EXISTS characters_workspace_category_fkey,
    DROP CONSTRAINT IF EXISTS characters_workspace_universe_fkey;

ALTER TABLE characters
    ADD CONSTRAINT characters_category_check
        CHECK (
            workspace_id <> 1
            OR category IS NULL
            OR category IN ('female', 'male', 'mf', 'mfm', 'mm', 'ff')
        ),
    ADD CONSTRAINT characters_universe_check
        CHECK (
            workspace_id <> 1
            OR universe IS NULL
            OR universe IN (
                'shs',
                'kr',
                'lm',
                'idm',
                'bg3',
                're',
                'lagerta',
                'original',
                'other'
            )
        );

CREATE TABLE IF NOT EXISTS workspace_character_story_links (
    workspace_id BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    character_id BIGINT NOT NULL,
    story_id BIGINT NOT NULL,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    assigned_by_user_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (character_id, story_id),
    FOREIGN KEY (workspace_id, character_id)
        REFERENCES characters(workspace_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (workspace_id, story_id)
        REFERENCES workspace_stories(workspace_id, id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_workspace_character_story_links_workspace
    ON workspace_character_story_links (workspace_id, character_id, is_primary, story_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_workspace_character_story_primary
    ON workspace_character_story_links (character_id)
    WHERE is_primary;
