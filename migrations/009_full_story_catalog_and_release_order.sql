ALTER TABLE character_stories
    ADD COLUMN IF NOT EXISTS release_order INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS released_on DATE,
    ADD COLUMN IF NOT EXISTS release_precision VARCHAR(8) NOT NULL DEFAULT 'unknown';

UPDATE character_stories
SET release_order = sort_order
WHERE release_order = 0;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'character_stories_release_precision_check'
    ) THEN
        ALTER TABLE character_stories
            ADD CONSTRAINT character_stories_release_precision_check
            CHECK (release_precision IN ('day', 'month', 'year', 'unknown'));
    END IF;
END
$$;

INSERT INTO character_stories (
    universe, key, short_label, title, sort_order,
    release_order, released_on, release_precision
)
VALUES
    ('kr', 'sails_in_fog', 'ПВТ', 'Паруса в тумане', 10, 10, '2018-01-01'::DATE, 'year'),
    ('kr', 'moonborn', 'РЛ', 'Рождённая Луной', 20, 20, '2018-01-01'::DATE, 'year'),
    ('kr', 'my_hollywood_story', 'МГИ', 'Моя Голливудская история', 30, 30, '2018-01-01'::DATE, 'year'),
    ('kr', 'queen_in_30_days', 'КЗ30Д', 'Королева за 30 дней', 40, 40, '2018-01-01'::DATE, 'year'),
    ('kr', 'shadows_of_saintfour', 'ТС', 'Тени Сентфора', 50, 50, '2019-01-01'::DATE, 'year'),
    ('kr', 'wave_patrol', 'ВП', 'Высокий прибой', 60, 60, '2019-01-01'::DATE, 'year'),
    ('kr', 'seduced_by_rhythm', 'ВРС', 'В ритме страсти', 70, 70, '2019-01-01'::DATE, 'year'),
    ('kr', 'chasing_you', 'ЯОНТ', 'Я охочусь на тебя', 80, 80, '2020-01-01'::DATE, 'year'),
    ('kr', 'heavens_secret', 'СН', 'Секрет Небес', 90, 90, '2020-01-01'::DATE, 'year'),
    ('kr', 'legend_of_willow', 'ЛИ', 'Легенда Ивы', 100, 100, '2020-01-01'::DATE, 'year'),
    ('kr', 'dracula_love_story', 'ДИЛ', 'Дракула: История любви', 110, 110, '2020-01-01'::DATE, 'year'),
    ('kr', 'love_from_outer_space', 'ЛСЗ', 'Любовь со звёзд', 120, 120, '2020-01-01'::DATE, 'year'),
    ('kr', 'path_of_valkyrie', 'ПВЛ', 'Путь Валькирии', 130, 130, '2020-01-01'::DATE, 'year'),
    ('kr', 'rage_of_titans', 'ЯТ', 'Ярость Титанов', 140, 140, '2021-01-01'::DATE, 'year'),
    ('kr', 'sophies_ten_wishes', '10ЖС', 'Десять желаний Софи', 150, 150, '2021-01-01'::DATE, 'year'),
    ('kr', 'sins_of_london', 'ГЛ', 'Грешный Лондон', 160, 160, '2021-01-01'::DATE, 'year'),
    ('kr', 'on_thin_ice', 'ПТЛ', 'По тонкому льду', 170, 170, '2021-01-01'::DATE, 'year'),
    ('kr', 'arcanum', 'АРК', 'Арканум', 180, 180, '2021-01-01'::DATE, 'year'),
    ('kr', 'gladiator_chronicles', 'ХГ', 'Хроники Гладиаторов', 190, 190, '2021-01-01'::DATE, 'year'),
    ('kr', 'heart_of_trespia', 'СТ', 'Сердце Треспии', 200, 200, '2021-01-01'::DATE, 'year'),
    ('kr', 'kali_call_of_darkness', 'КЗТ', 'Кали: Зов Тьмы', 210, 210, '2021-01-01'::DATE, 'year'),
    ('kr', 'flower_from_tiamats_fire', 'ЦИОТ', 'Цветок из Огня Тиамат', 220, 220, '2021-01-01'::DATE, 'year'),
    ('kr', 'theodora', 'ТЕО', 'Теодора', 230, 230, '2022-01-01'::DATE, 'year'),
    ('kr', 'through_storm_and_flame', 'СБИП', 'Сквозь бурю и пламя', 240, 240, '2022-01-01'::DATE, 'year'),
    ('kr', 'the_one', 'ИД', 'Идеал', 250, 250, '2022-01-01'::DATE, 'year'),
    ('kr', 'psi', 'ПСИ', 'Пси', 260, 260, '2022-01-01'::DATE, 'year'),
    ('kr', 'vying_for_versailles', 'ПВ', 'Покоряя Версаль', 270, 270, '2022-01-01'::DATE, 'year'),
    ('kr', 'desert_rose', 'РП', 'Роза пустыни', 280, 280, '2022-01-01'::DATE, 'year'),
    ('kr', 'heavens_secret_2', 'СН2', 'Секрет Небес 2', 290, 290, '2023-01-01'::DATE, 'year'),
    ('kr', 'elite_tag', 'ИТ', 'Игра в ТЭГ', 300, 300, '2023-01-01'::DATE, 'year'),
    ('kr', 'song_of_crimson_nile', 'ПОКН', 'Песнь о Красном Ниле', 310, 310, '2023-01-01'::DATE, 'year'),
    ('kr', 'chasing_you_2', 'ЯОНТ2', 'Я охочусь на тебя 2', 320, 320, '2023-01-01'::DATE, 'year'),
    ('kr', 'love_sin_evil', 'ЛГЗ', 'Любовь, Грех и Зло', 330, 330, '2023-01-01'::DATE, 'year'),
    ('kr', 'w_time_catcher', 'ЛВ', 'Ловчая Времени', 340, 340, '2023-01-01'::DATE, 'year'),
    ('kr', 'kali_flame_of_samsara', 'КПС', 'Кали: Пламя Сансары', 350, 350, '2023-01-01'::DATE, 'year'),
    ('kr', 'garden_of_eden', 'ЭС', 'Эдемов сад', 360, 360, '2023-01-01'::DATE, 'year'),
    ('kr', 'soulless', 'Б', 'Бездушная', 370, 370, '2023-01-01'::DATE, 'year'),
    ('kr', 'the_one_vol2', 'ИД2', 'Идеал. Том 2', 380, 380, '2024-01-01'::DATE, 'year'),
    ('kr', 'astreas_broken_heart', 'РСА', 'Разбитое сердце Астреи', 390, 390, '2024-01-01'::DATE, 'year'),
    ('kr', 'heavens_secret_requiem', 'СНР', 'Секрет Небес: Реквием', 400, 400, '2024-01-01'::DATE, 'year'),
    ('kr', 'seven_brothers', '7Б', 'Семь братьев', 410, 410, '2024-01-01'::DATE, 'year'),
    ('kr', 'and_haze_will_take_us', 'ИПНМ', 'И поглотит нас морок', 420, 420, '2024-01-01'::DATE, 'year'),
    ('kr', 'thunderstorms_saga', 'СОГ', 'Сага о грозах', 430, 430, '2024-01-01'::DATE, 'year'),
    ('kr', 'shakespeares_code', 'ШШ', 'Шифр Шекспира', 440, 440, '2024-01-01'::DATE, 'year'),
    ('kr', 'parallel_universes_bureau', 'БПМ', 'Бюро параллельных миров', 450, 450, '2024-01-01'::DATE, 'year'),
    ('kr', 'the_missing', 'ПР', 'Пропавшие', 460, 460, '2024-01-01'::DATE, 'year'),
    ('kr', 'arrival_number_3', 'П3', 'Пришествие №3', 470, 470, '2025-01-01'::DATE, 'year'),
    ('kr', 'te_amo_bay_of_hope', 'ТА', 'Te Amo: Залив надежды', 480, 480, '2025-01-01'::DATE, 'year'),
    ('kr', 'code_blue', 'КС', 'Код синий', 490, 490, '2025-01-01'::DATE, 'year'),
    ('kr', 'where_love_burns_forever', 'ТГЛГВ', 'Там, Где Любовь Горит Вечно', 500, 500, '2025-01-01'::DATE, 'year'),
    ('kr', 'heavens_secret_3', 'СН3', 'Секрет Небес 3', 510, 510, '2025-01-01'::DATE, 'year'),
    ('kr', 'parallel_universes_bureau_vol2', 'БПМ2', 'Бюро параллельных миров. Том 2', 520, 520, '2025-01-01'::DATE, 'year'),
    ('kr', 'te_amo_vol2_crystal_dream', 'ТА2', 'Te Amo. Том 2: Хрустальная мечта', 530, 530, '2025-01-01'::DATE, 'year'),
    ('kr', 'averris_child_of_rift', 'АДР', 'Аверрис: Дитя Разлома', 540, 540, '2025-01-01'::DATE, 'year'),
    ('kr', 'sins_asking_for_retribution', 'ГПВ', 'Грехи, просящие возмездия', 550, 550, '2025-01-01'::DATE, 'year'),
    ('kr', 'shadows_of_saintfour_2', 'ТС2', 'Тени Сентфора 2', 560, 560, '2026-01-01'::DATE, 'year'),
    ('kr', 'water_lily', 'ВЛ', 'Водяная Лилия', 570, 570, '2026-01-01'::DATE, 'year'),
    ('kr', 'born_of_sun', 'РС', 'Рождённая Солнцем', 580, 580, '2026-01-01'::DATE, 'year'),
    ('shs', 'illusion_glory', 'ИС', 'Иллюзия славы', 10, 10, '2023-01-01'::DATE, 'year'),
    ('shs', 'celestial_legend', 'ПОН', 'Предание о небожителях', 20, 20, '2023-01-01'::DATE, 'year'),
    ('shs', 'ragnarok_dragon_saga', 'СДР', 'Сага о драконе: Рагнарёк', 30, 30, '2024-01-01'::DATE, 'year'),
    ('shs', 'chains_of_agreement', 'ЦД', 'Цепи договора', 40, 40, '2024-01-01'::DATE, 'year'),
    ('shs', 'age_of_fatum', 'ЭФ', 'Эпоха Фатума', 50, 50, '2025-01-01'::DATE, 'year'),
    ('shs', 'deadly_biome', 'СБ', 'Смертельный Биом', 60, 60, '2026-01-01'::DATE, 'year'),
    ('shs', 'rome_temptation_of_wisdom', 'РИМ', 'Рим: Искушение Мудростью', 70, 70, '2026-01-01'::DATE, 'year'),
    ('lm', 'blooming_garden', 'ЦС', 'Цветущий сад', 10, 10, '2021-01-01'::DATE, 'year'),
    ('lm', 'gates_of_samhain', 'ВС', 'Врата Самайна', 20, 20, '2021-01-01'::DATE, 'year'),
    ('lm', 'when_sea_is_silent', 'КММ', 'Когда молчит море', 30, 30, '2021-01-01'::DATE, 'year'),
    ('lm', 'ark_dryden_chronicles', 'ХАД', 'Хроники Арк-Драйдена', 40, 40, '2022-01-01'::DATE, 'year'),
    ('lm', 'seal_of_nostradamus', 'ПН', 'Печать Нострадамуса', 50, 50, '2022-01-01'::DATE, 'year'),
    ('lm', 'tablet_of_isis', 'СИ', 'Скрижаль Исет', 60, 60, '2022-01-01'::DATE, 'year'),
    ('lm', 'nightmare_of_dark_forest', 'КТЛ', 'Кошмар Тёмного леса', 70, 70, '2023-01-01'::DATE, 'year'),
    ('lm', 'law_of_beast', 'ЗЗ', 'Закон Зверя', 80, 80, '2023-01-01'::DATE, 'year'),
    ('lm', 'lullaby_of_witches', 'КВ', 'Колыбель ведьм', 90, 90, '2023-01-01'::DATE, 'year'),
    ('lm', 'vampyrus_novus', 'ВН', 'Vampyrus Novus', 100, 100, '2024-01-01'::DATE, 'year'),
    ('lm', 'wandering_spirit', 'СД', 'Странствующий дух', 110, 110, '2024-01-01'::DATE, 'year'),
    ('lm', 'shadows_of_kailash', 'ТК', 'Тени Кайласа', 120, 120, '2025-01-01'::DATE, 'year'),
    ('lm', 'what_happened_in_vetwood_rock', 'ЧСВВР', 'Что случилось в Ветвуд-Роке?', 130, 130, '2025-01-01'::DATE, 'year'),
    ('lm', 'talents_of_menodora', 'ТМ', 'Таланты Менодоры', 140, 140, '2025-01-01'::DATE, 'year'),
    ('lm', 'last_victim', 'ПЖ', 'Последняя жертва', 150, 150, '2025-01-01'::DATE, 'year'),
    ('lm', 'tales_of_dungeons', 'СП', 'Сказки Подземелий', 160, 160, '2026-01-01'::DATE, 'year'),
    ('idm', 'legends_of_coraline_bay', 'ЛКБ', 'Легенды Коралин Бэй', 10, 10, '2025-01-01'::DATE, 'year'),
    ('lagerta', 'ghost', 'ПРЗ', 'ПРИЗРАК', 10, 10, NULL, 'unknown')
ON CONFLICT (universe, key) DO UPDATE
SET short_label = EXCLUDED.short_label,
    title = EXCLUDED.title,
    sort_order = EXCLUDED.sort_order,
    release_order = EXCLUDED.release_order,
    released_on = EXCLUDED.released_on,
    release_precision = EXCLUDED.release_precision;

DROP INDEX IF EXISTS idx_character_stories_universe_order;

CREATE INDEX IF NOT EXISTS idx_character_stories_universe_release_order
    ON character_stories(
        universe,
        release_order DESC,
        released_on DESC NULLS LAST,
        title,
        id
    );
