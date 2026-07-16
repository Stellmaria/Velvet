ALTER TABLE media_files
    ADD COLUMN IF NOT EXISTS visual_scan_status VARCHAR(16) NOT NULL DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS visual_scan_error TEXT,
    ADD COLUMN IF NOT EXISTS visual_scanned_at TIMESTAMPTZ;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'media_files_visual_scan_status_check'
    ) THEN
        ALTER TABLE media_files
            ADD CONSTRAINT media_files_visual_scan_status_check
            CHECK (visual_scan_status IN ('pending', 'processing', 'ready', 'skipped', 'error'));
    END IF;
END;
$$;

CREATE TABLE IF NOT EXISTS media_visual_fingerprints (
    media_id BIGINT PRIMARY KEY REFERENCES media_files(id) ON DELETE CASCADE,
    fingerprint_version SMALLINT NOT NULL DEFAULT 1,
    content_sha256 CHAR(64) NOT NULL,
    phash CHAR(16) NOT NULL,
    center_phash CHAR(16) NOT NULL,
    dhash CHAR(16) NOT NULL,
    ahash CHAR(16) NOT NULL,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    image_format VARCHAR(24),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (width > 0 AND height > 0)
);

CREATE INDEX IF NOT EXISTS idx_media_fingerprints_content_sha
    ON media_visual_fingerprints(content_sha256);

CREATE TABLE IF NOT EXISTS media_duplicate_candidates (
    id BIGSERIAL PRIMARY KEY,
    first_media_id BIGINT NOT NULL REFERENCES media_files(id) ON DELETE CASCADE,
    second_media_id BIGINT NOT NULL REFERENCES media_files(id) ON DELETE CASCADE,
    similarity_score SMALLINT NOT NULL,
    phash_distance SMALLINT NOT NULL,
    center_distance SMALLINT NOT NULL,
    dhash_distance SMALLINT NOT NULL,
    ahash_distance SMALLINT NOT NULL,
    exact_bytes BOOLEAN NOT NULL DEFAULT FALSE,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    decided_by BIGINT,
    decided_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (first_media_id < second_media_id),
    CHECK (similarity_score BETWEEN 0 AND 100),
    CHECK (status IN ('pending', 'confirmed', 'ignored')),
    UNIQUE (first_media_id, second_media_id)
);

CREATE INDEX IF NOT EXISTS idx_media_duplicates_status_score
    ON media_duplicate_candidates(status, similarity_score DESC, id);

CREATE TABLE IF NOT EXISTS media_file_checks (
    media_id BIGINT PRIMARY KEY REFERENCES media_files(id) ON DELETE CASCADE,
    status VARCHAR(16) NOT NULL DEFAULT 'unknown',
    checked_at TIMESTAMPTZ,
    error_text TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (status IN ('unknown', 'ok', 'broken'))
);

INSERT INTO media_file_checks (media_id)
SELECT id FROM media_files
ON CONFLICT (media_id) DO NOTHING;

CREATE INDEX IF NOT EXISTS idx_media_file_checks_status
    ON media_file_checks(status, checked_at NULLS FIRST);

UPDATE media_files
SET visual_scan_status = CASE
        WHEN media_type = 'photo'
          OR (media_type = 'document' AND COALESCE(mime_type, '') LIKE 'image/%')
        THEN 'pending'
        ELSE 'skipped'
    END,
    visual_scan_error = NULL
WHERE visual_scan_status = 'pending';

CREATE OR REPLACE FUNCTION initialize_media_quality_rows()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.visual_scan_status := CASE
        WHEN NEW.media_type = 'photo'
          OR (NEW.media_type = 'document' AND COALESCE(NEW.mime_type, '') LIKE 'image/%')
        THEN 'pending'
        ELSE 'skipped'
    END;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_initialize_media_quality_rows ON media_files;
CREATE TRIGGER trg_initialize_media_quality_rows
BEFORE INSERT ON media_files
FOR EACH ROW
EXECUTE FUNCTION initialize_media_quality_rows();

CREATE OR REPLACE FUNCTION create_media_file_check_row()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO media_file_checks (media_id)
    VALUES (NEW.id)
    ON CONFLICT (media_id) DO NOTHING;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_create_media_file_check_row ON media_files;
CREATE TRIGGER trg_create_media_file_check_row
AFTER INSERT ON media_files
FOR EACH ROW
EXECUTE FUNCTION create_media_file_check_row();
