CREATE TABLE IF NOT EXISTS workspace_creation_grants (
    user_id BIGINT PRIMARY KEY,
    granted_by_user_id BIGINT NOT NULL,
    allowed_modules TEXT[] NOT NULL DEFAULT ARRAY[
        'characters',
        'archive',
        'taxonomy',
        'references',
        'public_archive'
    ]::TEXT[],
    max_workspaces INTEGER NOT NULL DEFAULT 1 CHECK (max_workspaces BETWEEN 1 AND 10),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS workspace_modules (
    workspace_id BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    module_key VARCHAR(32) NOT NULL,
    is_allowed BOOLEAN NOT NULL DEFAULT TRUE,
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    updated_by_user_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (workspace_id, module_key),
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
            'team'
        )
    ),
    CHECK (is_allowed OR NOT is_enabled)
);

INSERT INTO workspace_modules (
    workspace_id,
    module_key,
    is_allowed,
    is_enabled,
    updated_by_user_id
)
SELECT
    1,
    module_key,
    TRUE,
    TRUE,
    7221553045
FROM unnest(ARRAY[
    'characters',
    'archive',
    'taxonomy',
    'references',
    'public_archive',
    'watermark',
    'qwen',
    'publications',
    'analytics',
    'team'
]::TEXT[]) AS module_key
ON CONFLICT (workspace_id, module_key) DO NOTHING;

CREATE TABLE IF NOT EXISTS workspace_categories (
    id BIGSERIAL PRIMARY KEY,
    workspace_id BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    key VARCHAR(64) NOT NULL,
    label VARCHAR(96) NOT NULL,
    emoji VARCHAR(16) NOT NULL DEFAULT '📁',
    sort_order INTEGER NOT NULL DEFAULT 100,
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_by_user_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (workspace_id, key)
);

CREATE INDEX IF NOT EXISTS idx_workspace_categories_enabled
    ON workspace_categories (workspace_id, is_enabled, sort_order, id);

CREATE TABLE IF NOT EXISTS workspace_universes (
    id BIGSERIAL PRIMARY KEY,
    workspace_id BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    key VARCHAR(64) NOT NULL,
    label VARCHAR(96) NOT NULL,
    emoji VARCHAR(16) NOT NULL DEFAULT '🎭',
    requires_story BOOLEAN NOT NULL DEFAULT FALSE,
    sort_order INTEGER NOT NULL DEFAULT 100,
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    source_workspace_id BIGINT REFERENCES workspaces(id) ON DELETE SET NULL,
    source_universe_key VARCHAR(64),
    created_by_user_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (workspace_id, key)
);

CREATE INDEX IF NOT EXISTS idx_workspace_universes_enabled
    ON workspace_universes (workspace_id, is_enabled, sort_order, id);

CREATE TABLE IF NOT EXISTS workspace_stories (
    id BIGSERIAL PRIMARY KEY,
    workspace_id BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    universe_key VARCHAR(64) NOT NULL,
    key VARCHAR(96) NOT NULL,
    short_label VARCHAR(32) NOT NULL,
    title VARCHAR(192) NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 100,
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    source_story_id BIGINT REFERENCES character_stories(id) ON DELETE SET NULL,
    created_by_user_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (workspace_id, universe_key, key),
    FOREIGN KEY (workspace_id, universe_key)
        REFERENCES workspace_universes(workspace_id, key)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_workspace_stories_enabled
    ON workspace_stories (workspace_id, universe_key, is_enabled, sort_order, id);

INSERT INTO workspace_categories (workspace_id, key, label, emoji, sort_order, created_by_user_id)
VALUES
    (1, 'female', 'Женский', '👩', 10, 7221553045),
    (1, 'male', 'Мужской', '👨', 20, 7221553045),
    (1, 'mf', 'МЖ', '👩‍❤️‍👨', 30, 7221553045),
    (1, 'mfm', 'МЖМ', '👨‍👩‍👨', 40, 7221553045),
    (1, 'mm', 'ММ', '👨‍❤️‍👨', 50, 7221553045),
    (1, 'ff', 'ЖЖ', '👩‍❤️‍👩', 60, 7221553045)
ON CONFLICT (workspace_id, key) DO NOTHING;

INSERT INTO workspace_universes (
    workspace_id,
    key,
    label,
    emoji,
    requires_story,
    sort_order,
    created_by_user_id
)
VALUES
    (1, 'shs', 'SHS', '🖤', TRUE, 10, 7221553045),
    (1, 'kr', 'КР', '💎', TRUE, 20, 7221553045),
    (1, 'lm', 'ЛМ', '🌙', TRUE, 30, 7221553045),
    (1, 'idm', 'ИДМ', '🕯', TRUE, 40, 7221553045),
    (1, 'bg3', 'BG3', '🎲', FALSE, 50, 7221553045),
    (1, 're', 'RE', '🧟', FALSE, 60, 7221553045),
    (1, 'lagerta', 'Лагерта', '⚔️', FALSE, 70, 7221553045),
    (1, 'original', 'Original', '✨', FALSE, 80, 7221553045),
    (1, 'other', 'Другое', '📂', FALSE, 90, 7221553045)
ON CONFLICT (workspace_id, key) DO NOTHING;

INSERT INTO workspace_stories (
    workspace_id,
    universe_key,
    key,
    short_label,
    title,
    sort_order,
    source_story_id,
    created_by_user_id
)
SELECT
    1,
    story.universe,
    story.key,
    story.short_label,
    story.title,
    COALESCE(story.release_order, story.sort_order, 100),
    story.id,
    7221553045
FROM character_stories AS story
JOIN workspace_universes AS universe
  ON universe.workspace_id = 1
 AND universe.key = story.universe
ON CONFLICT (workspace_id, universe_key, key) DO NOTHING;

UPDATE workspace_settings
SET public_archive_enabled = TRUE,
    updated_at = NOW()
WHERE workspace_id = 1;
