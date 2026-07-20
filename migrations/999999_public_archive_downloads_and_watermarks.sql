ALTER TABLE media_files
    ADD COLUMN IF NOT EXISTS source_telegram_file_id TEXT,
    ADD COLUMN IF NOT EXISTS watermark_applied BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS watermark_approved BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS watermark_approved_by BIGINT,
    ADD COLUMN IF NOT EXISTS watermark_approved_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS watermark_template JSONB;

CREATE TABLE IF NOT EXISTS public_media_view_stats (
    character_id BIGINT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    media_id BIGINT NOT NULL REFERENCES media_files(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL,
    view_count BIGINT NOT NULL DEFAULT 0,
    first_viewed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_viewed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (character_id, media_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_public_media_view_stats_media
    ON public_media_view_stats(character_id, media_id, last_viewed_at DESC);

CREATE TABLE IF NOT EXISTS public_media_download_stats (
    character_id BIGINT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    media_id BIGINT NOT NULL REFERENCES media_files(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL,
    download_count BIGINT NOT NULL DEFAULT 0,
    last_variant VARCHAR(24) NOT NULL DEFAULT 'original',
    first_downloaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_downloaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (character_id, media_id, user_id),
    CHECK (last_variant IN ('original', 'watermarked'))
);

CREATE INDEX IF NOT EXISTS idx_public_media_download_stats_media
    ON public_media_download_stats(character_id, media_id, last_downloaded_at DESC);
