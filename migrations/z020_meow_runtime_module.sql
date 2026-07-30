ALTER TABLE workspace_modules
    DROP CONSTRAINT IF EXISTS workspace_modules_module_key_check;

ALTER TABLE workspace_modules
    ADD CONSTRAINT workspace_modules_module_key_check
    CHECK (
        module_key IN (
            'characters',
            'archive',
            'taxonomy',
            'references',
            'public_archive',
            'watermark',
            'qwen',
            'publications',
            'analytics',
            'team',
            'meow'
        )
    );

CREATE TABLE IF NOT EXISTS meow_runtime_settings (
    singleton_id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (singleton_id = 1),
    kie_concurrency_limit INTEGER NOT NULL DEFAULT 100
        CHECK (kie_concurrency_limit BETWEEN 1 AND 100),
    grs_concurrency_limit INTEGER NOT NULL DEFAULT 100
        CHECK (grs_concurrency_limit BETWEEN 1 AND 100),
    workspace_default_limit INTEGER NOT NULL DEFAULT 5
        CHECK (workspace_default_limit BETWEEN 1 AND 20),
    workspace_max_limit INTEGER NOT NULL DEFAULT 20
        CHECK (workspace_max_limit BETWEEN 1 AND 20),
    configured BOOLEAN NOT NULL DEFAULT FALSE,
    setup_notice_sent_at TIMESTAMPTZ,
    updated_by_user_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO meow_runtime_settings (singleton_id)
VALUES (1)
ON CONFLICT (singleton_id) DO NOTHING;

CREATE TABLE IF NOT EXISTS workspace_meow_settings (
    workspace_id BIGINT PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,
    concurrency_limit INTEGER NOT NULL DEFAULT 5
        CHECK (concurrency_limit BETWEEN 1 AND 20),
    updated_by_user_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO workspace_meow_settings (workspace_id)
SELECT workspace.id
FROM workspaces AS workspace
ON CONFLICT (workspace_id) DO NOTHING;

CREATE TABLE IF NOT EXISTS workspace_user_module_preferences (
    workspace_id BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL,
    module_key VARCHAR(64) NOT NULL,
    is_visible BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (workspace_id, user_id, module_key)
);

CREATE INDEX IF NOT EXISTS workspace_user_module_preferences_user_idx
    ON workspace_user_module_preferences (user_id, workspace_id);

INSERT INTO workspace_modules (
    workspace_id,
    module_key,
    is_allowed,
    is_enabled,
    updated_by_user_id
)
SELECT
    workspace.id,
    'meow',
    workspace.is_system,
    workspace.is_system,
    NULL
FROM workspaces AS workspace
ON CONFLICT (workspace_id, module_key) DO NOTHING;
