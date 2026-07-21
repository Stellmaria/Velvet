CREATE TABLE IF NOT EXISTS workspaces (
    id BIGSERIAL PRIMARY KEY,
    slug VARCHAR(64) NOT NULL UNIQUE,
    name VARCHAR(128) NOT NULL,
    is_system BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO workspaces (id, slug, name, is_system)
VALUES (1, 'velvet', 'Velvet Anatomy', TRUE)
ON CONFLICT (id) DO UPDATE
SET slug = EXCLUDED.slug,
    name = EXCLUDED.name,
    is_system = TRUE;

SELECT setval(
    pg_get_serial_sequence('workspaces', 'id'),
    GREATEST((SELECT COALESCE(MAX(id), 1) FROM workspaces), 1),
    TRUE
);

CREATE TABLE IF NOT EXISTS workspace_members (
    workspace_id BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL,
    role VARCHAR(16) NOT NULL CHECK (
        role IN ('owner', 'admin', 'editor', 'reviewer', 'viewer')
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (workspace_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_workspace_members_user
    ON workspace_members (user_id, workspace_id);

CREATE TABLE IF NOT EXISTS workspace_settings (
    workspace_id BIGINT PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,
    timezone VARCHAR(64) NOT NULL DEFAULT 'Europe/Warsaw',
    public_archive_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    downloads_mode VARCHAR(16) NOT NULL DEFAULT 'disabled' CHECK (
        downloads_mode IN ('disabled', 'watermark', 'original')
    ),
    qwen_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO workspace_settings (workspace_id, public_archive_enabled, qwen_enabled)
VALUES (1, TRUE, TRUE)
ON CONFLICT (workspace_id) DO NOTHING;

CREATE TABLE IF NOT EXISTS workspace_channels (
    workspace_id BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    kind VARCHAR(24) NOT NULL CHECK (
        kind IN (
            'archive',
            'public',
            'publication',
            'adult',
            'discussion',
            'logs',
            'analytics'
        )
    ),
    chat_id BIGINT NOT NULL,
    url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (workspace_id, kind)
);

CREATE INDEX IF NOT EXISTS idx_workspace_channels_chat
    ON workspace_channels (chat_id, workspace_id);

ALTER TABLE characters
    ADD COLUMN IF NOT EXISTS workspace_id BIGINT;

UPDATE characters
SET workspace_id = 1
WHERE workspace_id IS NULL;

ALTER TABLE characters
    ALTER COLUMN workspace_id SET DEFAULT 1,
    ALTER COLUMN workspace_id SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'characters_workspace_id_fkey'
          AND conrelid = 'characters'::regclass
    ) THEN
        ALTER TABLE characters
            ADD CONSTRAINT characters_workspace_id_fkey
            FOREIGN KEY (workspace_id)
            REFERENCES workspaces(id)
            ON DELETE RESTRICT;
    END IF;
END
$$;

ALTER TABLE characters
    DROP CONSTRAINT IF EXISTS characters_normalized_name_key;

CREATE UNIQUE INDEX IF NOT EXISTS uq_characters_workspace_normalized_name
    ON characters (workspace_id, normalized_name);

CREATE INDEX IF NOT EXISTS idx_characters_workspace_name
    ON characters (workspace_id, normalized_name, id);
