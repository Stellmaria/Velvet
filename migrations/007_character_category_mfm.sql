ALTER TABLE characters
    DROP CONSTRAINT IF EXISTS characters_category_check;

ALTER TABLE characters
    ADD CONSTRAINT characters_category_check
    CHECK (
        category IS NULL
        OR category IN ('female', 'male', 'mf', 'mfm', 'mm', 'ff')
    );
