# Сессия: перенос Characters и Stories presentation

- Дата: 2026-07-19
- ID: `2026-07-19-p3c-characters-stories-presentation`
- Линия/фаза: Velvet Archive, P3C
- Статус: `завершено`
- Ветка: `agent/p3c-characters-stories`
- Базовый commit: `b38c0d74e6ec681af197f98b645ddb545cdbfd98`

## Перед началом

### Цель

Перенести связный набор Telegram controllers персонажей и историй из legacy `velvet_bot/handlers` в канонические presentation-пакеты, сохранив команды, callback prefixes, порядок регистрации, старые import paths и поведение существующего бота.

### Исходный контекст

P3A–P3B собрали четыре ordered router bundles. Первый P3C-срез перенёс Supervisor/System и сократил активные legacy handler implementations до 59. Следующим измеримым доменом назначены characters/stories: профили, алиасы, каталог, некатегоризированные карточки, назначение вселенных и одиночных/множественных историй.

### Планируемый объём

- создать канонические пакеты `presentation/telegram/routers/characters` и `stories`;
- перенести девять активных controller implementations без изменения их содержимого;
- заменить старые handler-файлы module aliases того же canonical module object;
- перевести `archive_and_public` bundle на канонические imports при прежнем порядке регистрации;
- добавить regression-тесты module identity, ownership и composition;
- обновить architecture inventory и зафиксировать следующий P3C-срез.

### Критерии готовности

- девять canonical modules содержат реальные Router implementations;
- девять legacy handler paths не содержат decorators или business logic;
- старые и новые imports возвращают один module object;
- активный bundle использует только canonical paths для перенесённого домена;
- количество активных legacy implementations уменьшается с 59 до 50;
- command/callback composition остаётся 55 routers без дублей;
- обязательные GitHub Actions завершаются успешно.

### Риски и ограничения

Главный риск — import cycles между каталогом персонажей, одиночными историями, KR multi-story и profile overrides. Поэтому implementations переносятся байт-в-байт, старые paths сохраняются как полные module aliases, а порядок router registration не меняется. Бизнес-рефакторинг и переименование callback data в этот срез не входят.

## После завершения

### Фактически сделано

- созданы отдельные canonical packages `characters` и `stories`;
- девять существующих implementations перенесены с сохранением исходных blob SHA;
- legacy modules заменены короткими aliases через `importlib` и `sys.modules`;
- `archive_and_public.py` импортирует перенесённые routers из canonical presentation paths;
- порядок всех 32 routers в bundle сохранён;
- добавлен отдельный P3C regression-контракт и обновлён общий composition contract;
- Phase 9 architecture contract переведён с legacy source paths на canonical implementations;
- architecture inventory фиксирует 50 implementations и 18 aliases;
- следующим доменом назначены reference presentation controllers.

### Миграции и совместимость

Миграции PostgreSQL не требуются и не изменялись. Slash-команды, callback prefixes, тексты, application use cases и порядок регистрации сохранены. Старые `velvet_bot.handlers.*` paths остаются совместимыми с существующими imports и `unittest.mock.patch`.

### Проверки

- первый tests run #966 выполнил 853 теста и выявил четыре устаревших Phase 9 source-path ожидания; runtime/import regressions не обнаружены;
- Phase 9 contract обновлён на canonical controller paths commit `9fe2a5af832a4946829cabf54914f21a3f757e36`;
- финальный tests run #967: 853 теста, success;
- docker build #503: success;
- project notes contract #366: success;
- architecture inventory: root imports 0, active routers 55, duplicates 0, implementations 50, aliases 18.

### PR и commit

- PR: #197 `Move characters and stories controllers into presentation`;
- implementation commit: `f7ccce33679e616a8c71e51b41251b3496995270`;
- contract fix commit: `9fe2a5af832a4946829cabf54914f21a3f757e36`;
- ветка: `agent/p3c-characters-stories`.

### Незавершённое

Внутренние imports между частью перенесённых controllers пока могут проходить через сохранённые legacy aliases. Это не меняет module identity и подтверждено полным тестовым набором, но прямое выравнивание внутренних imports следует выполнять отдельным узким cleanup-срезом, не смешивая его с физическим переносом.

### Следующий шаг

После merge PR #197 продолжить P3C перенос reference controllers из `velvet_bot/handlers` в канонический presentation package с тем же module-alias контрактом.
