ALTER TABLE characters
    ADD COLUMN IF NOT EXISTS universe VARCHAR(16);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'characters_universe_check'
    ) THEN
        ALTER TABLE characters
            ADD CONSTRAINT characters_universe_check
            CHECK (
                universe IS NULL OR universe IN (
                    'shs', 'kr', 'lm', 'idm', 'bg3', 'lagerta', 'original'
                )
            );
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_characters_category_universe_name
    ON characters(category, universe, normalized_name, id);
