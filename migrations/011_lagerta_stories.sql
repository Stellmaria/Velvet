DO $$
DECLARE
    ghost_id BIGINT;
BEGIN
    SELECT id INTO ghost_id
    FROM character_stories
    WHERE universe = 'lagerta' AND key = 'ghost'
    LIMIT 1;

    IF ghost_id IS NOT NULL THEN
        UPDATE character_stories
        SET key = 'mansion_on_the_hill',
            short_label = 'ОНХ',
            title = 'Особняк на холме',
            sort_order = 10,
            release_order = 10,
            released_on = NULL,
            release_precision = 'unknown'
        WHERE id = ghost_id;
    ELSE
        INSERT INTO character_stories (
            universe, key, short_label, title, sort_order,
            release_order, released_on, release_precision
        )
        VALUES (
            'lagerta', 'mansion_on_the_hill', 'ОНХ',
            'Особняк на холме', 10, 10, NULL, 'unknown'
        )
        ON CONFLICT (universe, key) DO UPDATE
        SET short_label = EXCLUDED.short_label,
            title = EXCLUDED.title,
            sort_order = EXCLUDED.sort_order,
            release_order = EXCLUDED.release_order;
    END IF;
END;
$$;

INSERT INTO character_stories (
    universe, key, short_label, title, sort_order,
    release_order, released_on, release_precision
)
VALUES (
    'lagerta', 'edge_of_night', 'ПН',
    'Предел ночи', 20, 20, NULL, 'unknown'
)
ON CONFLICT (universe, key) DO UPDATE
SET short_label = EXCLUDED.short_label,
    title = EXCLUDED.title,
    sort_order = EXCLUDED.sort_order,
    release_order = EXCLUDED.release_order;
