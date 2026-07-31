-- Explicit pre-send and ambiguous post-send states prevent automatic duplicate delivery.

ALTER TABLE media_delivery_jobs
    DROP CONSTRAINT IF EXISTS media_delivery_jobs_notification_status_check;
ALTER TABLE media_delivery_jobs
    ADD CONSTRAINT media_delivery_jobs_notification_status_check
    CHECK (notification_status IN (
        'pending',
        'sending',
        'success',
        'failed',
        'expired',
        'skipped',
        'uncertain'
    ));

ALTER TABLE media_delivery_items
    DROP CONSTRAINT IF EXISTS media_delivery_items_download_status_check;
ALTER TABLE media_delivery_items
    ADD CONSTRAINT media_delivery_items_download_status_check
    CHECK (download_status IN (
        'pending',
        'success',
        'failed',
        'expired',
        'skipped'
    ));

ALTER TABLE media_delivery_items
    DROP CONSTRAINT IF EXISTS media_delivery_items_original_status_check;
ALTER TABLE media_delivery_items
    ADD CONSTRAINT media_delivery_items_original_status_check
    CHECK (original_status IN (
        'pending',
        'sending',
        'success',
        'failed',
        'expired',
        'skipped',
        'uncertain'
    ));

ALTER TABLE media_delivery_items
    DROP CONSTRAINT IF EXISTS media_delivery_items_preview_status_check;
ALTER TABLE media_delivery_items
    ADD CONSTRAINT media_delivery_items_preview_status_check
    CHECK (preview_status IN (
        'pending',
        'sending',
        'success',
        'failed',
        'expired',
        'skipped',
        'uncertain'
    ));
