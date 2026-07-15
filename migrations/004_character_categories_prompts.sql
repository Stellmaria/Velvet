ALTER TABLE characters
    ADD COLUMN IF NOT EXISTS category VARCHAR(16),
    ADD COLUMN IF NOT EXISTS prompt_post_url TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'characters_category_check'
    ) THEN
        ALTER TABLE characters
            ADD CONSTRAINT characters_category_check
            CHECK (category IS NULL OR category IN ('female', 'male', 'mf', 'mm', 'ff'));
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_characters_category_name
    ON characters(category, normalized_name, id);
