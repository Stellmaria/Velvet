ALTER TABLE media_files
    ADD COLUMN IF NOT EXISTS watermark_storage_chat_id BIGINT,
    ADD COLUMN IF NOT EXISTS watermark_storage_thread_id BIGINT,
    ADD COLUMN IF NOT EXISTS watermark_storage_message_id BIGINT,
    ADD COLUMN IF NOT EXISTS watermark_storage_file_id TEXT,
    ADD COLUMN IF NOT EXISTS watermark_storage_file_unique_id TEXT,
    ADD COLUMN IF NOT EXISTS watermark_storage_file_size BIGINT,
    ADD COLUMN IF NOT EXISTS watermark_storage_sha256 CHAR(64),
    ADD COLUMN IF NOT EXISTS watermark_stored_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS watermark_local_cleaned_at TIMESTAMPTZ;

CREATE UNIQUE INDEX IF NOT EXISTS uq_media_watermark_storage_message
    ON media_files(watermark_storage_chat_id, watermark_storage_message_id)
    WHERE watermark_storage_chat_id IS NOT NULL
      AND watermark_storage_message_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_media_watermark_storage_sha256
    ON media_files(watermark_storage_sha256)
    WHERE watermark_storage_sha256 IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_media_watermark_storage_file_id
    ON media_files(watermark_storage_file_id)
    WHERE watermark_storage_file_id IS NOT NULL;
