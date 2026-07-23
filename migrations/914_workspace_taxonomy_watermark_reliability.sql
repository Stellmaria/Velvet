ALTER TABLE characters
    ALTER COLUMN category TYPE VARCHAR(64),
    ALTER COLUMN universe TYPE VARCHAR(64);

ALTER TABLE workspace_stories
    ADD COLUMN IF NOT EXISTS emoji VARCHAR(16) NOT NULL DEFAULT '📖';

CREATE TABLE IF NOT EXISTS workspace_watermark_templates (
    workspace_id BIGINT PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,
    position VARCHAR(32) NOT NULL DEFAULT 'bottom_right',
    color VARCHAR(16) NOT NULL DEFAULT 'auto',
    opacity INTEGER NOT NULL DEFAULT 70 CHECK (opacity BETWEEN 1 AND 100),
    size DOUBLE PRECISION NOT NULL DEFAULT 19.7 CHECK (size BETWEEN 3.0 AND 70.0),
    margin DOUBLE PRECISION NOT NULL DEFAULT 4.4 CHECK (margin BETWEEN 0.0 AND 30.0),
    lock_layer BOOLEAN NOT NULL DEFAULT TRUE,
    updated_by_user_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (
        position IN (
            'top_left', 'top_center', 'top_right',
            'center_left', 'center', 'center_right',
            'bottom_left', 'bottom_center', 'bottom_right'
        )
    ),
    CHECK (color = 'auto' OR color ~ '^#[0-9a-fA-F]{6}$')
);

COMMENT ON TABLE workspace_watermark_templates IS
    'Default watermark settings applied to new jobs in one personal workspace.';
