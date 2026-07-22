CREATE TABLE IF NOT EXISTS workspace_watermark_assets (
    workspace_id BIGINT PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,
    asset_kind VARCHAR(16) NOT NULL CHECK (asset_kind IN ('svg', 'png')),
    telegram_file_id TEXT NOT NULL,
    telegram_file_unique_id TEXT,
    file_name TEXT NOT NULL,
    mime_type VARCHAR(64) NOT NULL,
    file_size BIGINT NOT NULL CHECK (file_size > 0),
    local_path TEXT NOT NULL,
    content_sha256 CHAR(64) NOT NULL,
    width DOUBLE PRECISION NOT NULL CHECK (width > 0),
    height DOUBLE PRECISION NOT NULL CHECK (height > 0),
    has_alpha BOOLEAN NOT NULL DEFAULT TRUE,
    uploaded_by BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_workspace_watermark_assets_sha256
    ON workspace_watermark_assets(content_sha256);

ALTER TABLE watermark_jobs
    ADD COLUMN IF NOT EXISTS workspace_id BIGINT,
    ADD COLUMN IF NOT EXISTS logo_kind VARCHAR(16) NOT NULL DEFAULT 'builtin',
    ADD COLUMN IF NOT EXISTS logo_path TEXT,
    ADD COLUMN IF NOT EXISTS logo_width DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS logo_height DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS logo_name TEXT;

UPDATE watermark_jobs
SET workspace_id = 1
WHERE workspace_id IS NULL;

ALTER TABLE watermark_jobs
    ALTER COLUMN workspace_id SET DEFAULT 1,
    ALTER COLUMN workspace_id SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'watermark_jobs_workspace_id_fkey'
          AND conrelid = 'watermark_jobs'::regclass
    ) THEN
        ALTER TABLE watermark_jobs
            ADD CONSTRAINT watermark_jobs_workspace_id_fkey
            FOREIGN KEY (workspace_id)
            REFERENCES workspaces(id)
            ON DELETE RESTRICT;
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'watermark_jobs_logo_kind_check'
          AND conrelid = 'watermark_jobs'::regclass
    ) THEN
        ALTER TABLE watermark_jobs
            ADD CONSTRAINT watermark_jobs_logo_kind_check
            CHECK (logo_kind IN ('builtin', 'svg', 'png'));
    END IF;
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'watermark_jobs_logo_snapshot_check'
          AND conrelid = 'watermark_jobs'::regclass
    ) THEN
        ALTER TABLE watermark_jobs
            ADD CONSTRAINT watermark_jobs_logo_snapshot_check
            CHECK (
                logo_kind = 'builtin'
                OR (
                    logo_path IS NOT NULL
                    AND logo_width IS NOT NULL AND logo_width > 0
                    AND logo_height IS NOT NULL AND logo_height > 0
                )
            );
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_watermark_jobs_workspace_updated
    ON watermark_jobs(workspace_id, updated_at DESC);

CREATE OR REPLACE FUNCTION protect_last_workspace_owner()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    remaining_owners INTEGER;
BEGIN
    IF OLD.role <> 'owner' THEN
        RETURN OLD;
    END IF;
    IF TG_OP = 'UPDATE' AND NEW.role = 'owner' THEN
        RETURN NEW;
    END IF;

    PERFORM pg_advisory_xact_lock(OLD.workspace_id);
    SELECT COUNT(*)
    INTO remaining_owners
    FROM workspace_members
    WHERE workspace_id = OLD.workspace_id
      AND role = 'owner'
      AND user_id <> OLD.user_id;

    IF remaining_owners = 0 THEN
        RAISE EXCEPTION 'Нельзя удалить или понизить последнего владельца пространства.'
            USING ERRCODE = '23514';
    END IF;
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

DROP TRIGGER IF EXISTS trg_protect_last_workspace_owner
    ON workspace_members;

CREATE TRIGGER trg_protect_last_workspace_owner
BEFORE DELETE OR UPDATE OF role
ON workspace_members
FOR EACH ROW
EXECUTE FUNCTION protect_last_workspace_owner();
