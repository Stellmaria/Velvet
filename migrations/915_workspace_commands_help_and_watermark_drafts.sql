ALTER TABLE workspace_settings
    ADD COLUMN IF NOT EXISTS show_button_hints BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE watermark_revisions
    DROP CONSTRAINT IF EXISTS watermark_revisions_status_check;

ALTER TABLE watermark_revisions
    ADD CONSTRAINT watermark_revisions_status_check
    CHECK (status IN ('draft', 'pending', 'processing', 'ready', 'error'));
