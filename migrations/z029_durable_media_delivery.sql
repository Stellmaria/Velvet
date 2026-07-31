-- Durable provider-result and Telegram-delivery state for paid media generation.

CREATE TABLE IF NOT EXISTS media_delivery_jobs (
    task_id UUID PRIMARY KEY REFERENCES ai_tasks(id) ON DELETE CASCADE,
    provider VARCHAR(32) NOT NULL,
    provider_task_id TEXT NOT NULL,
    chat_id BIGINT,
    media_kind VARCHAR(16) NOT NULL,
    request_metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    status VARCHAR(32) NOT NULL DEFAULT 'provider_submitted',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    result_resolution_attempts INTEGER NOT NULL DEFAULT 0,
    result_resolution_error TEXT,
    notification_status VARCHAR(16) NOT NULL DEFAULT 'pending',
    notification_error TEXT,
    last_error TEXT,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    locked_by VARCHAR(160),
    locked_at TIMESTAMPTZ,
    provider_submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    provider_success_at TIMESTAMPTZ,
    result_resolved_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT media_delivery_jobs_provider_task_unique
        UNIQUE (provider, provider_task_id, task_id),
    CONSTRAINT media_delivery_jobs_media_kind_check
        CHECK (media_kind IN ('image', 'video')),
    CONSTRAINT media_delivery_jobs_status_check
        CHECK (status IN (
            'provider_submitted',
            'provider_success',
            'result_resolved',
            'delivering',
            'retry',
            'delivered',
            'partial',
            'expired',
            'failed'
        )),
    CONSTRAINT media_delivery_jobs_notification_status_check
        CHECK (notification_status IN ('pending', 'success', 'failed', 'expired', 'skipped')),
    CONSTRAINT media_delivery_jobs_attempt_count_check
        CHECK (attempt_count >= 0 AND result_resolution_attempts >= 0)
);

CREATE TABLE IF NOT EXISTS media_delivery_items (
    task_id UUID NOT NULL REFERENCES media_delivery_jobs(task_id) ON DELETE CASCADE,
    result_index INTEGER NOT NULL,
    result_url TEXT NOT NULL,
    url_status VARCHAR(16) NOT NULL DEFAULT 'available',
    download_status VARCHAR(16) NOT NULL DEFAULT 'pending',
    original_status VARCHAR(16) NOT NULL DEFAULT 'pending',
    preview_status VARCHAR(16) NOT NULL DEFAULT 'pending',
    content_type VARCHAR(255),
    file_name TEXT,
    download_attempts INTEGER NOT NULL DEFAULT 0,
    original_attempts INTEGER NOT NULL DEFAULT 0,
    preview_attempts INTEGER NOT NULL DEFAULT 0,
    download_error TEXT,
    original_error TEXT,
    preview_error TEXT,
    resolved_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    downloaded_at TIMESTAMPTZ,
    original_sent_at TIMESTAMPTZ,
    preview_sent_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (task_id, result_index),
    CONSTRAINT media_delivery_items_result_index_check
        CHECK (result_index > 0),
    CONSTRAINT media_delivery_items_url_status_check
        CHECK (url_status IN ('available', 'expired', 'unreachable')),
    CONSTRAINT media_delivery_items_download_status_check
        CHECK (download_status IN ('pending', 'success', 'failed', 'expired', 'skipped')),
    CONSTRAINT media_delivery_items_original_status_check
        CHECK (original_status IN ('pending', 'success', 'failed', 'expired', 'skipped')),
    CONSTRAINT media_delivery_items_preview_status_check
        CHECK (preview_status IN ('pending', 'success', 'failed', 'expired', 'skipped')),
    CONSTRAINT media_delivery_items_attempts_check
        CHECK (download_attempts >= 0 AND original_attempts >= 0 AND preview_attempts >= 0)
);

CREATE INDEX IF NOT EXISTS idx_media_delivery_jobs_due
    ON media_delivery_jobs (next_attempt_at, created_at)
    WHERE status IN ('result_resolved', 'retry', 'delivering');
CREATE INDEX IF NOT EXISTS idx_media_delivery_jobs_provider_task
    ON media_delivery_jobs (provider, provider_task_id);
CREATE INDEX IF NOT EXISTS idx_media_delivery_items_url_status
    ON media_delivery_items (url_status, updated_at);
