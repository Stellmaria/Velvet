-- Keep the active Seven Hearts Stories catalog aligned with the application.
-- Release order follows the official story numbering. Slot 40 is intentionally
-- unused: the original "Миссия Фортуна" was removed and its rewritten version
-- returned as release №16.
INSERT INTO character_stories (
    universe,
    key,
    short_label,
    title,
    sort_order,
    release_order,
    released_on,
    release_precision
)
VALUES
    ('shs', 'celestial_legend', 'ПОН', 'Предание о небожителях', 10, 10, '2023-01-01'::DATE, 'year'),
    ('shs', 'villains_last_wish', 'ПЖЗ', 'Последнее Желание Злодейки', 20, 20, '2023-01-01'::DATE, 'year'),
    ('shs', 'age_of_fatum', 'ЭФ', 'Эпоха Фатума', 30, 30, '2023-01-01'::DATE, 'year'),
    ('shs', 'heart_of_atlanta', 'СА', 'Сердце Атланта', 50, 50, '2023-01-01'::DATE, 'year'),
    ('shs', 'bride_for_vampire', 'НДВ', 'Невеста для Вампира', 60, 60, '2023-01-01'::DATE, 'year'),
    ('shs', 'deadly_biome', 'СБ', 'Смертельный Биом', 70, 70, '2024-01-01'::DATE, 'year'),
    ('shs', 'illusion_glory', 'ИС', 'Иллюзия славы', 80, 80, '2024-01-01'::DATE, 'year'),
    ('shs', 'ragnarok_dragon_saga', 'СДР', 'Сага о драконе: Рагнарёк', 90, 90, '2024-01-01'::DATE, 'year'),
    ('shs', 'legacy_of_almazar', 'НА', 'Наследие Алмазара', 100, 100, '2024-01-01'::DATE, 'year'),
    ('shs', 'chains_of_agreement', 'ЦД', 'Цепи договора', 110, 110, '2025-01-01'::DATE, 'year'),
    ('shs', 'child_of_abyss', 'ДБ', 'Дитя Бездны', 120, 120, '2025-01-01'::DATE, 'year'),
    ('shs', 'morvain', 'МОР', 'Морвэйн', 130, 130, '2026-01-01'::DATE, 'year'),
    ('shs', 'frame_49', 'К49', 'Кадр 49', 140, 140, '2026-01-01'::DATE, 'year'),
    ('shs', 'rome_temptation_of_wisdom', 'РИМ', 'Рим: Искушение Мудростью', 150, 150, '2026-01-01'::DATE, 'year'),
    ('shs', 'mission_fortune', 'МФ', 'Миссия Фортуна', 160, 160, '2026-01-01'::DATE, 'year')
ON CONFLICT (universe, key) DO UPDATE
SET short_label = EXCLUDED.short_label,
    title = EXCLUDED.title,
    sort_order = EXCLUDED.sort_order,
    release_order = EXCLUDED.release_order,
    released_on = EXCLUDED.released_on,
    release_precision = EXCLUDED.release_precision;
