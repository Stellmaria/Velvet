ALTER TABLE telegram_storage_objects
    DROP CONSTRAINT IF EXISTS telegram_storage_objects_kind_check;

ALTER TABLE telegram_storage_objects
    ADD CONSTRAINT telegram_storage_objects_kind_check CHECK (
        storage_kind IN (
            'watermarks',
            'backups',
            'diagnostics',
            'exports',
            'codex',
            'releases',
            'rework',
            'inbox',
            'analysis'
        )
    );

CREATE TABLE IF NOT EXISTS telegram_storage_analysis_jobs (
    id BIGSERIAL PRIMARY KEY,
    storage_object_id BIGINT NOT NULL UNIQUE
        REFERENCES telegram_storage_objects(id) ON DELETE CASCADE,
    status VARCHAR(16) NOT NULL DEFAULT 'queued',
    priority INTEGER NOT NULL DEFAULT 0,
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    max_attempts INTEGER NOT NULL DEFAULT 3 CHECK (max_attempts BETWEEN 1 AND 20),
    available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    locked_at TIMESTAMPTZ,
    worker_id TEXT,
    hermes_run_id TEXT,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    CONSTRAINT telegram_storage_analysis_jobs_status_check CHECK (
        status IN ('queued', 'running', 'completed', 'failed', 'skipped')
    )
);

CREATE INDEX IF NOT EXISTS idx_telegram_storage_analysis_jobs_claim
    ON telegram_storage_analysis_jobs(priority DESC, available_at, id)
    WHERE status = 'queued';

CREATE INDEX IF NOT EXISTS idx_telegram_storage_analysis_jobs_status
    ON telegram_storage_analysis_jobs(status, updated_at DESC);

CREATE TABLE IF NOT EXISTS telegram_storage_analysis (
    storage_object_id BIGINT PRIMARY KEY
        REFERENCES telegram_storage_objects(id) ON DELETE CASCADE,
    analyzer TEXT NOT NULL,
    analyzer_version TEXT NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'completed',
    summary TEXT NOT NULL DEFAULT '',
    tags JSONB NOT NULL DEFAULT '[]'::JSONB,
    entities JSONB NOT NULL DEFAULT '[]'::JSONB,
    action_items JSONB NOT NULL DEFAULT '[]'::JSONB,
    text_excerpt TEXT,
    sensitivity VARCHAR(16) NOT NULL DEFAULT 'normal',
    confidence SMALLINT,
    hermes_run_id TEXT,
    usage JSONB NOT NULL DEFAULT '{}'::JSONB,
    raw_response JSONB NOT NULL DEFAULT '{}'::JSONB,
    error_message TEXT,
    analyzed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT telegram_storage_analysis_status_check CHECK (
        status IN ('completed', 'failed', 'skipped')
    ),
    CONSTRAINT telegram_storage_analysis_sensitivity_check CHECK (
        sensitivity IN ('normal', 'sensitive', 'restricted')
    ),
    CONSTRAINT telegram_storage_analysis_confidence_check CHECK (
        confidence IS NULL OR confidence BETWEEN 0 AND 100
    )
);

CREATE INDEX IF NOT EXISTS idx_telegram_storage_analysis_analyzed
    ON telegram_storage_analysis(analyzed_at DESC, storage_object_id DESC);

CREATE INDEX IF NOT EXISTS idx_telegram_storage_analysis_tags
    ON telegram_storage_analysis USING GIN(tags);

CREATE INDEX IF NOT EXISTS idx_telegram_storage_analysis_entities
    ON telegram_storage_analysis USING GIN(entities);
