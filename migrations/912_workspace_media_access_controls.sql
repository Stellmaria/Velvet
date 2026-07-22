ALTER TABLE workspace_settings
    DROP CONSTRAINT IF EXISTS workspace_settings_downloads_mode_check;

ALTER TABLE workspace_settings
    ADD CONSTRAINT workspace_settings_downloads_mode_check
    CHECK (downloads_mode IN ('disabled', 'watermark', 'original', 'subscription'));

COMMENT ON COLUMN workspace_settings.downloads_mode IS
    'Public download policy: disabled, approved watermark copy, original, or original after membership check in the workspace public channel.';
