# Сессия: понятная навигация и мастер личного пространства

- Дата: 22 июля 2026 года
- ID: `2026-07-22-workspace-guided-navigation`
- Линия/фаза: Velvet Archive / стабилизация personal workspace UX
- Статус: `частично`
- Ветка: текущая локальная ветка
- Базовый commit: `0c2ca41d47498c641d6422f89bd10175b1512c0b`

## Перед началом

### Цель

Сделать уже перенесённые функции личного пространства доступными из понятного кнопочного интерфейса и усилить существующий мастер первого запуска объяснениями, не открывая пользователям системные owner-инструменты Velvet Anatomy.

### Исходный контекст

Личные characters, archive, references, publications, analytics, team и watermark имеют отдельные workspace boundaries, однако вход из домашнего меню есть не для всех модулей. Мастер `workspace_onboarding` существует, но не связан с домашним экраном как основной путь обучения. Qwen Quality Center и импорт Telegram пока не имеют полного tenant-aware переноса.

### Планируемый объём

- добавить из домашнего пространства кнопочный вход в уже существующие personal publications и analytics;
- сделать видимый вход в мастер настройки и краткий гид;
- показать пользователю честное пояснение для функций, которые ещё не готовы как личный модуль;
- добавить регрессионные тесты маршрутов и UI-контракта;
- не менять системные Supervisor, backup, Codex, diagnostics, global Quality Center и Telegram export import.

### Критерии готовности

- владелец личного пространства открывает мастер без slash-команды;
- включённые publications и analytics открываются кнопками и повторно проверяют роль/module policy;
- пользователь не видит Qwen как готовый самостоятельный личный центр, если такой маршрут отсутствует;
- тесты доказывают соответствие кнопок доступным обработчикам;
- production-код не получает SQL в Telegram handlers.

### Риски и ограничения

Это UX-улучшение существующих контуров, а не перенос всего owner-инструментария. Живая Telegram-проверка и PostgreSQL integration tests требуют целевого окружения; `README.md` уже изменён пользователем и не входит в срез.

## После завершения

### Фактически сделано

- из домашнего меню личного пространства добавлен заметный вход «🧭 Настройка и гид» в существующий мастер первого запуска;
- включённый модуль publications открывает tenant-aware центр черновиков кнопкой, с прежней проверкой роли editor, module policy и publication channel;
- включённый модуль analytics открывает tenant-aware dashboard кнопкой, с прежней проверкой роли reviewer, module policy и аналитического канала;
- publication callback вынесен в отдельный entry router, чтобы его ранняя регистрация не перехватывала media/reply сценарии публикаций раньше archive/reference handlers;
- гид объясняет, что кнопками выполняются ежедневные операции, а `/workspace_bind` остаётся необходимым исключением: команда должна быть отправлена внутри конкретного Telegram-чата или темы;
- описание Qwen приведено к фактической границе: comparison через личные references доступно, а общий Quality Center, медиасеты и AI-очередь пока системные;
- добавлен regression contract на мастер, module-entry routes и порядок router registration; обновлён generated Telegram navigation inventory.

### Изменённые модули и контракты

- `workspace_owner_controls`, `workspace_onboarding`, `workspace_ui`;
- `workspace_publications` и `workspace_analytics` получили guarded `wsp:module:*` entries;
- `archive_and_public` разделяет ранний publication entry router и поздний publication capture router;
- `tests/test_workspace_guided_navigation.py` фиксирует новый UX-contract.

### Миграции и совместимость

Миграции не требуются. Существующие slash-команды остаются аварийным и context-required входом; системные owner-функции не раскрываются личным пространствам.

### Проверки

- `.venv\\Scripts\\python.exe -m compileall -q velvet_bot tests` — success;
- `.venv\\Scripts\\python.exe -m unittest tests.test_workspace_guided_navigation tests.test_workspace_onboarding tests.test_workspace_product_access tests.test_workspace_publication_queues tests.test_workspace_analytics tests.test_workspace_team_watermark tests.test_telegram_navigation_inventory -q` — 62 tests success, 25 PostgreSQL tests skipped without `TEST_DATABASE_URL`;
- `.venv\\Scripts\\python.exe scripts/telegram_navigation_inventory.py --root velvet_bot --check` — 655 inline buttons, 0 violations;
- `git diff --check` не может быть полностью зелёным из-за существующих conflict markers в пользовательском `README.md`; файлы данного среза whitespace errors не показали.

### PR и commit

Не созданы.

### Незавершённое

- живая Telegram-проверка owner flow: `/start` → «Моё пространство» → «Настройка и гид», затем вход в publications и analytics;
- PostgreSQL integration run с `TEST_DATABASE_URL`;
- полноценный tenant-aware Qwen/Quality Center, media sets и Telegram export import остаются отдельными срезами;
- отдельный dashboard для team members и единый конфигурируемый global-owner identity не включены в этот UX-срез.

### Следующий шаг

Спроектировать tenant-aware Qwen/Quality Center с отдельными workspace-scoped job/repository boundaries, не открывая системные AI-задачи Velvet Anatomy другим пользователям.
