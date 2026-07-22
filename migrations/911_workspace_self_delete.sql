ALTER TABLE characters
    DROP CONSTRAINT IF EXISTS characters_workspace_id_fkey;

ALTER TABLE characters
    ADD CONSTRAINT characters_workspace_id_fkey
    FOREIGN KEY (workspace_id)
    REFERENCES workspaces(id)
    ON DELETE CASCADE;

ALTER TABLE watermark_jobs
    DROP CONSTRAINT IF EXISTS watermark_jobs_workspace_id_fkey;

ALTER TABLE watermark_jobs
    ADD CONSTRAINT watermark_jobs_workspace_id_fkey
    FOREIGN KEY (workspace_id)
    REFERENCES workspaces(id)
    ON DELETE CASCADE;
