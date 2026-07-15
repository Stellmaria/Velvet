CREATE TABLE IF NOT EXISTS character_stories (
    id BIGSERIAL PRIMARY KEY,
    universe VARCHAR(16) NOT NULL,
    key VARCHAR(64) NOT NULL,
    short_label VARCHAR(16) NOT NULL,
    title VARCHAR(160) NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT character_stories_universe_check
        CHECK (universe IN ('shs', 'kr', 'lm', 'idm', 'bg3', 'lagerta', 'original')),
    CONSTRAINT character_stories_universe_key_unique UNIQUE (universe, key),
    CONSTRAINT character_stories_universe_short_unique UNIQUE (universe, short_label)
);

ALTER TABLE characters
    ADD COLUMN IF NOT EXISTS story_id BIGINT
        REFERENCES character_stories(id)
        ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_character_stories_universe_order
    ON character_stories(universe, sort_order, title, id);

CREATE INDEX IF NOT EXISTS idx_characters_story_name
    ON characters(story_id, normalized_name, id);

INSERT INTO character_stories (universe, key, short_label, title, sort_order)
VALUES
    ('shs', 'illusion_glory', 'ИС', 'Иллюзия славы', 10),
    ('shs', 'celestial_legend', 'ПОН', 'Предание о небожителях', 20),
    ('shs', 'ragnarok_dragon_saga', 'СДР', 'Сага о драконе Рагнарёк', 30),
    ('shs', 'chains_of_agreement', 'ЦД', 'Цепи договора', 40),
    ('shs', 'age_of_fatum', 'ЭФ', 'Эпоха Фатума', 50),
    ('kr', 'sails_in_fog', 'ПВТ', 'Паруса в тумане', 10),
    ('kr', 'moonborn', 'РЛ', 'Рождённая Луной', 20),
    ('kr', 'my_hollywood_story', 'МГИ', 'Моя голливудская история', 30),
    ('kr', 'queen_in_30_days', 'КЗ30Д', 'Королева за 30 дней', 40),
    ('kr', 'shadows_of_saintfour', 'ТС', 'Тени Сентфора', 50),
    ('kr', 'wave_patrol', 'ВП', 'Высокий прибой', 60),
    ('kr', 'seduced_by_rhythm', 'ВРС', 'В ритме страсти', 70),
    ('kr', 'chasing_you', 'ОЗТ', 'Охотница за тобой', 80),
    ('kr', 'heavens_secret', 'СН', 'Секрет Небес', 90),
    ('kr', 'legend_of_willow', 'ЛИ', 'Легенда Ивы', 100),
    ('kr', 'dracula_love_story', 'ДИЛ', 'Дракула. История любви', 110),
    ('kr', 'love_from_outer_space', 'ЛСЗ', 'Любовь со звёзд', 120),
    ('kr', 'path_of_valkyrie', 'ПВЛ', 'Путь Валькирии', 130),
    ('kr', 'rage_of_titans', 'ЯТ', 'Ярость Титанов', 140),
    ('kr', 'sophies_ten_wishes', '10ЖС', '10 желаний Софи', 150),
    ('kr', 'sins_of_london', 'ГЛ', 'Грешный Лондон', 160),
    ('kr', 'on_thin_ice', 'ПТЛ', 'По тонкому льду', 170),
    ('kr', 'arcanum', 'АРК', 'Арканум', 180),
    ('kr', 'gladiator_chronicles', 'ХГ', 'Хроники Гладиаторов', 190),
    ('kr', 'heart_of_trespia', 'СТ', 'Сердце Треспии', 200),
    ('kr', 'kali_call_of_darkness', 'КЗТ', 'Кали. Зов тьмы', 210),
    ('kr', 'flower_from_tiamats_fire', 'ЦИОТ', 'Цветок из огня Тиамат', 220),
    ('kr', 'the_one', 'ИД', 'Идеал', 230),
    ('kr', 'theodora', 'ТЕО', 'Теодора', 240),
    ('kr', 'psi', 'ПСИ', 'Пси', 250),
    ('kr', 'vying_for_versailles', 'ПВ', 'Покоряя Версаль', 260),
    ('kr', 'desert_rose', 'РП', 'Роза пустыни', 270),
    ('kr', 'heavens_secret_2', 'СН2', 'Секрет Небес 2', 280),
    ('kr', 'elite_tag', 'ИТ', 'Игра в ТЭГ', 290),
    ('kr', 'song_of_crimson_nile', 'ПОКН', 'Песнь о Красном Ниле', 300),
    ('kr', 'chasing_you_2', 'ОЗТ2', 'Охотница за тобой 2', 310),
    ('kr', 'love_sin_evil', 'ЛГЗ', 'Любовь, грех и зло', 320),
    ('kr', 'w_time_catcher', 'ЛВ', 'W: Ловчая времени', 330),
    ('kr', 'garden_of_eden', 'ЭС', 'Эдемов сад', 340),
    ('kr', 'kali_flame_of_samsara', 'КПС', 'Кали: Пламя Сансары', 350),
    ('kr', 'soulless', 'Б', 'Бездушная', 360),
    ('kr', 'astreas_broken_heart', 'РСА', 'Разбитое сердце Астреи', 370),
    ('kr', 'heavens_secret_requiem', 'СНР', 'Секрет Небес: Реквием', 380),
    ('kr', 'thunderstorms_saga', 'СОГ', 'Сага о Грозах', 390),
    ('kr', 'and_haze_will_take_us', 'ИПНМ', 'И поглотит нас морок', 400),
    ('kr', 'seven_brothers', '7Б', 'Семь Братьев', 410),
    ('kr', 'parallel_universes_bureau', 'БПМ', 'Бюро Параллельных Миров', 420),
    ('kr', 'shakespeares_code', 'КШ', 'Код Шекспира', 430),
    ('lm', 'blooming_garden', 'ЦС', 'Цветущий сад', 10),
    ('lm', 'gates_of_samhain', 'ВС', 'Врата Самайна', 20),
    ('lm', 'when_sea_is_silent', 'КММ', 'Когда молчит море', 30),
    ('lm', 'ark_dryden_chronicles', 'ХАД', 'Хроники Арк-Драйдена', 40),
    ('lm', 'seal_of_nostradamus', 'ПН', 'Печать Нострадамуса', 50),
    ('lm', 'tablet_of_isis', 'СИ', 'Скрижаль Исет', 60),
    ('lm', 'nightmare_of_dark_forest', 'КТЛ', 'Кошмар Тёмного леса', 70),
    ('lm', 'law_of_beast', 'ЗЗ', 'Закон Зверя', 80),
    ('lm', 'lullaby_of_witches', 'КВ', 'Колыбель ведьм', 90),
    ('lm', 'vampyrus_novus', 'ВН', 'Vampyrus Novus', 100),
    ('lm', 'wandering_spirit', 'СД', 'Странствующий дух', 110),
    ('lm', 'last_victim', 'ПЖ', 'Последняя жертва', 120),
    ('idm', 'legends_of_coraline_bay', 'ЛКБ', 'Легенды Коралин Бэй', 10)
ON CONFLICT (universe, key) DO UPDATE
SET short_label = EXCLUDED.short_label,
    title = EXCLUDED.title,
    sort_order = EXCLUDED.sort_order;
