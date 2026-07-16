ALTER TABLE media_files
    ADD COLUMN IF NOT EXISTS preview_file_id TEXT,
    ADD COLUMN IF NOT EXISTS preview_file_unique_id TEXT,
    ADD COLUMN IF NOT EXISTS preview_width INTEGER,
    ADD COLUMN IF NOT EXISTS preview_height INTEGER,
    ADD COLUMN IF NOT EXISTS preview_source VARCHAR(32),
    ADD COLUMN IF NOT EXISTS preview_updated_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_media_files_missing_image_preview
    ON media_files(id)
    WHERE media_type = 'document'
      AND COALESCE(mime_type, '') LIKE 'image/%'
      AND preview_file_id IS NULL;
