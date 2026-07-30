ALTER TABLE watermark_revisions
    ADD COLUMN IF NOT EXISTS remote_worker_id TEXT,
    ADD COLUMN IF NOT EXISTS remote_lease_token_hash TEXT,
    ADD COLUMN IF NOT EXISTS remote_lease_expires_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS remote_heartbeat_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS watermark_revisions_remote_lease_idx
    ON watermark_revisions (remote_lease_expires_at)
    WHERE status = 'processing' AND remote_worker_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS krita_remote_workers (
    worker_id TEXT PRIMARY KEY,
    version TEXT,
    hostname TEXT,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    active_job_id BIGINT,
    active_revision INTEGER,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS krita_remote_workers_last_seen_idx
    ON krita_remote_workers (last_seen_at DESC);
