CREATE TABLE IF NOT EXISTS workspace_video_templates (
    workspace_id BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    model VARCHAR(16) NOT NULL CHECK (model IN ('seedance', 'wan')),
    resolution VARCHAR(8) NOT NULL,
    duration_seconds INTEGER NOT NULL CHECK (duration_seconds BETWEEN 2 AND 15),
    generate_audio BOOLEAN NOT NULL DEFAULT FALSE,
    wan_mode VARCHAR(16) NOT NULL DEFAULT 'first' CHECK (
        wan_mode IN ('first', 'first_last')
    ),
    updated_by_user_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (workspace_id, model),
    CHECK (
        (model = 'seedance' AND resolution IN ('480p', '720p', '1080p'))
        OR (model = 'wan' AND resolution IN ('720p', '1080p'))
    ),
    CHECK (model = 'seedance' OR NOT generate_audio),
    CHECK (model = 'wan' OR wan_mode = 'first')
);

COMMENT ON TABLE workspace_video_templates IS
    'One editable standard video-generation template per workspace and provider model.';
