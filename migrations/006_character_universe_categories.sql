ALTER TABLE characters
    ADD COLUMN IF NOT EXISTS universe_category VARCHAR(16);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'characters_universe_category_check'
    ) THEN
        ALTER TABLE characters
            ADD CONSTRAINT characters_universe_category_check
            CHECK (
                universe_category IS NULL
                OR universe_category IN ('shs', 'kr', 'lm', 'lagerta', 'original')
            );
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_characters_type_universe_name
    ON characters(category, universe_category, normalized_name, id);

CREATE INDEX IF NOT EXISTS idx_characters_universe_name
    ON characters(universe_category, normalized_name, id);
