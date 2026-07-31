-- Typed, redacted failure metadata and an explicit uncertain Telegram-send state.

ALTER TABLE media_delivery_jobs
    ADD COLUMN IF NOT EXISTS result_resolution_error_code VARCHAR(96),
    ADD COLUMN IF NOT EXISTS result_resolution_error_fingerprint VARCHAR(32),
    ADD COLUMN IF NOT EXISTS notification_error_code VARCHAR(96),
    ADD COLUMN IF NOT EXISTS notification_error_fingerprint VARCHAR(32),
    ADD COLUMN IF NOT EXISTS last_error_code VARCHAR(96),
    ADD COLUMN IF NOT EXISTS last_error_fingerprint VARCHAR(32);

ALTER TABLE media_delivery_items
    ADD COLUMN IF NOT EXISTS download_error_code VARCHAR(96),
    ADD COLUMN IF NOT EXISTS download_error_fingerprint VARCHAR(32),
    ADD COLUMN IF NOT EXISTS original_error_code VARCHAR(96),
    ADD COLUMN IF NOT EXISTS original_error_fingerprint VARCHAR(32),
    ADD COLUMN IF NOT EXISTS preview_error_code VARCHAR(96),
    ADD COLUMN IF NOT EXISTS preview_error_fingerprint VARCHAR(32);

ALTER TABLE media_delivery_jobs
    DROP CONSTRAINT IF EXISTS media_delivery_jobs_notification_status_check;
ALTER TABLE media_delivery_jobs
    ADD CONSTRAINT media_delivery_jobs_notification_status_check
    CHECK (notification_status IN (
        'pending', 'uncertain', 'success', 'failed', 'expired', 'skipped'
    ));

ALTER TABLE media_delivery_items
    DROP CONSTRAINT IF EXISTS media_delivery_items_original_status_check;
ALTER TABLE media_delivery_items
    ADD CONSTRAINT media_delivery_items_original_status_check
    CHECK (original_status IN (
        'pending', 'uncertain', 'success', 'failed', 'expired', 'skipped'
    ));

ALTER TABLE media_delivery_items
    DROP CONSTRAINT IF EXISTS media_delivery_items_preview_status_check;
ALTER TABLE media_delivery_items
    ADD CONSTRAINT media_delivery_items_preview_status_check
    CHECK (preview_status IN (
        'pending', 'uncertain', 'success', 'failed', 'expired', 'skipped'
    ));
