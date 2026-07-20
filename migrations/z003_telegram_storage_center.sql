CREATE TABLE IF NOT EXISTS telegram_storage_objects (
    id BIGSERIAL PRIMARY KEY,
    storage_kind VARCHAR(32) NOT NULL,
    logical_key TEXT NOT NULL,
    original_name TEXT NOT NULL,
    source_path TEXT,
    mime_type TEXT,
    size_bytes BIGINT NOT NULL CHECK (size_bytes >= 0),
    sha256 CHAR(64) NOT NULL,
    encrypted BOOLEAN NOT NULL DEFAULT FALSE,
    encryption_version TEXT,
    chat_id BIGINT NOT NULL,
    thread_id BIGINT,
    part_count INTEGER NOT NULL DEFAULT 1 CHECK (part_count > 0),
    manifest JSONB NOT NULL DEFAULT '{}'::JSONB,
    migrated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    local_deleted_at TIMESTAMPTZ,
    CONSTRAINT telegram_storage_objects_kind_check CHECK (
        storage_kind IN (
            'watermarks',
            'backups',
            'diagnostics',
            'exports',
            'codex',
            'releases',
            'rework'
        )
    ),
    CONSTRAINT telegram_storage_objects_identity_unique
        UNIQUE (storage_kind, logical_key, sha256)
);

CREATE TABLE IF NOT EXISTS telegram_storage_parts (
    storage_object_id BIGINT NOT NULL
        REFERENCES telegram_storage_objects(id) ON DELETE CASCADE,
    part_number INTEGER NOT NULL CHECK (part_number > 0),
    message_id BIGINT NOT NULL,
    telegram_file_id TEXT NOT NULL,
    telegram_file_unique_id TEXT,
    size_bytes BIGINT NOT NULL CHECK (size_bytes >= 0),
    sha256 CHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (storage_object_id, part_number),
    CONSTRAINT telegram_storage_parts_message_unique
        UNIQUE (storage_object_id, message_id)
);

CREATE INDEX IF NOT EXISTS idx_telegram_storage_objects_kind_migrated
    ON telegram_storage_objects(storage_kind, migrated_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_telegram_storage_objects_sha256
    ON telegram_storage_objects(sha256);

CREATE INDEX IF NOT EXISTS idx_telegram_storage_objects_logical_key
    ON telegram_storage_objects(storage_kind, logical_key);

CREATE TABLE IF NOT EXISTS telegram_storage_migration_runs (
    id BIGSERIAL PRIMARY KEY,
    migration_kind VARCHAR(32) NOT NULL DEFAULT 'manual',
    status VARCHAR(16) NOT NULL DEFAULT 'running',
    requested_by BIGINT,
    discovered_files INTEGER NOT NULL DEFAULT 0,
    stored_files INTEGER NOT NULL DEFAULT 0,
    skipped_files INTEGER NOT NULL DEFAULT 0,
    failed_files INTEGER NOT NULL DEFAULT 0,
    deleted_files INTEGER NOT NULL DEFAULT 0,
    freed_bytes BIGINT NOT NULL DEFAULT 0,
    details JSONB NOT NULL DEFAULT '{}'::JSONB,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    CONSTRAINT telegram_storage_migration_kind_check CHECK (
        migration_kind IN ('initial_full', 'manual', 'resume')
    ),
    CONSTRAINT telegram_storage_migration_status_check CHECK (
        status IN ('running', 'completed', 'partial', 'failed')
    )
);

CREATE INDEX IF NOT EXISTS idx_telegram_storage_migration_runs_started
    ON telegram_storage_migration_runs(started_at DESC, id DESC);

ALTER TABLE backup_runs
    ADD COLUMN IF NOT EXISTS telegram_storage_object_id BIGINT
        REFERENCES telegram_storage_objects(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS offloaded_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_backup_runs_storage_object
    ON backup_runs(telegram_storage_object_id)
    WHERE telegram_storage_object_id IS NOT NULL;
