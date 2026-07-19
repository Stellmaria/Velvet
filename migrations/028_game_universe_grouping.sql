ALTER TABLE characters
    DROP CONSTRAINT IF EXISTS characters_universe_check;

ALTER TABLE characters
    ADD CONSTRAINT characters_universe_check
    CHECK (
        universe IS NULL OR universe IN (
            'shs',
            'kr',
            'lm',
            'idm',
            'bg3',
            're',
            'lagerta',
            'original',
            'other'
        )
    );
