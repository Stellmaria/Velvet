ALTER TABLE workspace_settings
    ADD COLUMN IF NOT EXISTS download_audience VARCHAR(16) NOT NULL DEFAULT 'disabled',
    ADD COLUMN IF NOT EXISTS download_variant VARCHAR(16) NOT NULL DEFAULT 'watermark';

UPDATE workspace_settings
SET download_audience = CASE downloads_mode
        WHEN 'disabled' THEN 'disabled'
        WHEN 'subscription' THEN 'subscribers'
        ELSE 'all'
    END,
    download_variant = CASE downloads_mode
        WHEN 'original' THEN 'original'
        WHEN 'subscription' THEN 'original'
        ELSE 'watermark'
    END;

ALTER TABLE workspace_settings
    DROP CONSTRAINT IF EXISTS workspace_settings_download_audience_check,
    DROP CONSTRAINT IF EXISTS workspace_settings_download_variant_check;

ALTER TABLE workspace_settings
    ADD CONSTRAINT workspace_settings_download_audience_check
        CHECK (download_audience IN ('disabled', 'all', 'subscribers')),
    ADD CONSTRAINT workspace_settings_download_variant_check
        CHECK (download_variant IN ('watermark', 'original'));

COMMENT ON COLUMN workspace_settings.download_audience IS
    'Who may use the explicit public download action: disabled, all, or members of the configured download channel.';
COMMENT ON COLUMN workspace_settings.download_variant IS
    'Which file public download returns: approved watermark copy or preserved original.';

ALTER TABLE workspace_destinations
    DROP CONSTRAINT IF EXISTS workspace_destinations_destination_key_check;

ALTER TABLE workspace_destinations
    ADD CONSTRAINT workspace_destinations_destination_key_check
    CHECK (
        destination_key IN (
            'characters',
            'media',
            'references',
            'public',
            'adult',
            'downloads',
            'watermarks',
            'publications',
            'discussion',
            'analytics',
            'logs'
        )
    );

ALTER TABLE workspace_channels
    DROP CONSTRAINT IF EXISTS workspace_channels_kind_check;

ALTER TABLE workspace_channels
    ADD CONSTRAINT workspace_channels_kind_check
    CHECK (
        kind IN (
            'archive',
            'public',
            'download',
            'publication',
            'adult',
            'discussion',
            'logs',
            'analytics'
        )
    );

CREATE TABLE IF NOT EXISTS workspace_media_owner_favorites (
    workspace_id BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    character_id BIGINT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    media_id BIGINT NOT NULL REFERENCES media_files(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (workspace_id, character_id, media_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_workspace_media_owner_favorites_media
    ON workspace_media_owner_favorites(workspace_id, character_id, media_id);
