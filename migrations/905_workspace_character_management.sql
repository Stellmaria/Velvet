CREATE TABLE IF NOT EXISTS workspace_character_aliases (
    id BIGSERIAL PRIMARY KEY,
    workspace_id BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    character_id BIGINT NOT NULL,
    alias VARCHAR(64) NOT NULL,
    normalized_alias VARCHAR(64) NOT NULL,
    source VARCHAR(16) NOT NULL DEFAULT 'manual',
    created_by BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT workspace_character_aliases_source_check
        CHECK (source IN ('name', 'manual', 'import')),
    CONSTRAINT workspace_character_aliases_character_fkey
        FOREIGN KEY (workspace_id, character_id)
        REFERENCES characters(workspace_id, id)
        ON DELETE CASCADE,
    CONSTRAINT workspace_character_aliases_workspace_alias_unique
        UNIQUE (workspace_id, normalized_alias),
    CONSTRAINT workspace_character_aliases_character_alias_unique
        UNIQUE (character_id, normalized_alias)
);

CREATE INDEX IF NOT EXISTS idx_workspace_character_aliases_character
    ON workspace_character_aliases (
        workspace_id,
        character_id,
        source,
        alias,
        id
    );

INSERT INTO workspace_character_aliases (
    workspace_id,
    character_id,
    alias,
    normalized_alias,
    source
)
SELECT
    character.workspace_id,
    character.id,
    character.name,
    LOWER(REGEXP_REPLACE(character.name, '[^[:alnum:]]+', '', 'g')),
    'name'
FROM characters AS character
WHERE REGEXP_REPLACE(character.name, '[^[:alnum:]]+', '', 'g') <> ''
ON CONFLICT (workspace_id, normalized_alias) DO NOTHING;
