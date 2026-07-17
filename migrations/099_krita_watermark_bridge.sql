CREATE TABLE IF NOT EXISTS watermark_jobs (
    id BIGSERIAL PRIMARY KEY,
    owner_user_id BIGINT NOT NULL,
    chat_id BIGINT NOT NULL,
    source_message_id BIGINT NOT NULL,
    source_file_id TEXT NOT NULL,
    source_file_unique_id TEXT,
    source_path TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'approved', 'cancelled')),
    current_revision INTEGER NOT NULL DEFAULT 1 CHECK (current_revision > 0),
    control_message_id BIGINT,
    preview_message_id BIGINT,
    final_path TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS watermark_revisions (
    job_id BIGINT NOT NULL REFERENCES watermark_jobs(id) ON DELETE CASCADE,
    revision INTEGER NOT NULL CHECK (revision > 0),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    position TEXT NOT NULL,
    color TEXT NOT NULL,
    opacity INTEGER NOT NULL CHECK (opacity BETWEEN 1 AND 100),
    size NUMERIC(5, 1) NOT NULL CHECK (size BETWEEN 3.0 AND 70.0),
    margin NUMERIC(5, 1) NOT NULL CHECK (margin BETWEEN 0.0 AND 30.0),
    lock_layer BOOLEAN NOT NULL DEFAULT TRUE,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'processing', 'ready', 'error')),
    request_path TEXT,
    output_path TEXT,
    response_path TEXT,
    telegram_preview_file_id TEXT,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    PRIMARY KEY (job_id, revision)
);

CREATE INDEX IF NOT EXISTS watermark_revisions_status_created_idx
    ON watermark_revisions (status, created_at);
CREATE INDEX IF NOT EXISTS watermark_jobs_owner_updated_idx
    ON watermark_jobs (owner_user_id, updated_at DESC);
