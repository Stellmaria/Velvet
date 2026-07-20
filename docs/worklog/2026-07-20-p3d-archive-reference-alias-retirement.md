# Сессия: P3D retirement archive/reference aliases

- Дата: 2026-07-20
- ID: `2026-07-20-p3d-archive-reference-alias-retirement`
- Линия/фаза: Velvet Archive, P3D
- Статус: `завершено`
- Ветка: `agent/p3d-archive-reference-alias-retirement`
- Базовый commit: `cf697a4e3f9770fd532771c31375f1a94fb238f7`

## Перед началом

### Цель

Мигрировать archive/reference compatibility-тесты на canonical presentation modules и удалить первую проверенную группу старых `velvet_bot.handlers.*` aliases.

### Исходный контекст

Production legacy-consumer inventory уже закрыт на `0 / 0 / 0`, но в `velvet_bot/handlers` оставались 68 module aliases. Значительная часть archive/reference aliases использовалась только тестами, которые продолжали импортировать старые paths и тем самым искусственно удерживали compatibility-слой.

### Планируемый объём

- перевести archive/public/reference tests на canonical modules;
- заменить patch/import strings старых paths;
- удалить archive/reference aliases после нулевого repository reference count;
- добавить отдельный inventory consumers handler aliases;
- обновить architecture inventory и документы;
- не менять callback prefixes, команды, SQL и пользовательское поведение.

### Критерии готовности

- удалённые aliases не имеют repository references;
- canonical tests сохраняют прежние boundary и regression проверки;
- inventory не содержит references на отсутствующие aliases;
- production legacy-consumer baseline остаётся `0 / 0 / 0`;
- полный test suite, Docker build и project notes contract проходят.

### Риски и ограничения

Удаляется только связанная группа, для которой все тестовые imports и dynamic patch paths переведены на canonical modules. Остальные aliases сохраняются до миграции их tests/contracts.

## После завершения

### Фактически сделано

- archive/public compatibility tests переведены на canonical controllers;
- reference compatibility tests переведены на canonical controllers;
- удалены 22 aliases archive/reference группы;
- количество handler aliases уменьшено с 68 до 46;
- добавлен `handler_alias_consumer_inventory`, который учитывает imports, from-imports, literal module references и динамические prefix references;
- inventory блокирует references на уже удалённые aliases;
- production legacy-consumer inventory сохранён на `0 / 0 / 0`;
- callback prefixes, commands, SQL и пользовательские тексты не изменены.

### Удалённые aliases

- archive/public: `admin_large_media_preview`, `admin_media_display`, `admin_media_spoiler`, `archive`, `discussion_updates`, `guest_archive`, `inline_help`, `media_browser`, `media_prompt_binding`, `public_archive`, `public_manager`, `public_media_display`, `public_notification_open`, `spoiler_save`, `start`, `telegram_analytics_import`;
- references: `reference_albums`, `reference_comparison`, `reference_comparison_help`, `reference_documents`, `reference_management`, `references`.

### Миграции и совместимость

Миграции не требуются. Удалены только Python import facades, не используемые production-кодом. Внешние Telegram contracts не менялись.

### Проверки

- целевой canonical/inventory suite: 19 tests + 91 subtests, success;
- alias inventory, legacy inventory и architecture inventory checks: success;
- полный локальный suite: 924 tests, success; 24 PostgreSQL integration tests skipped без `TEST_DATABASE_URL`;
- финальные GitHub Actions фиксируются на head PR #223.

### PR и commit

- PR: #223 `P3D: retire archive and reference handler aliases`;
- ветка: `agent/p3d-archive-reference-alias-retirement`;
- verified production tree применён commit `397771ffc229a2e23532c9d2a6f05b2249cb654e`;
- финальный user-authored head создан после очистки transport files.

### Незавершённое

Остаются 46 handler aliases, из которых 44 имеют repository references, а 2 (`ai_jobs`, `quality_calibration`) уже не используются внутри репозитория. Также остаются 8 runtime compatibility components, 114 root modules и неоднородное размещение repositories.

### Следующий шаг

Удалить два уже неиспользуемых aliases отдельным минимальным срезом и мигрировать следующую связанную группу character/story либо analytics/core. После сокращения compatibility-слоя перейти к P3E repository/root module layout.
