# Сессия: P3D retirement zero-reference aliases

- Дата: 2026-07-20
- ID: `2026-07-20-p3d-zero-reference-alias-retirement`
- Линия/фаза: Velvet Archive, P3D
- Статус: `завершено`
- Ветка: `agent/p3d-zero-reference-alias-retirement`
- Базовый commit: `551a7e93236534b3814a92c81ed32a7112b998b3`

## Перед началом

### Цель

Удалить два handler aliases, для которых alias-consumer inventory уже подтверждает нулевой repository reference count: `ai_jobs` и `quality_calibration`.

### Исходный контекст

После PR #223 в `velvet_bot/handlers` остаются 46 aliases. Из них 44 имеют repository references, а `ai_jobs` и `quality_calibration` не используются ни production-кодом, ни тестами, ни динамическими строковыми paths.

### Планируемый объём

- удалить `velvet_bot/handlers/ai_jobs.py`;
- удалить `velvet_bot/handlers/quality_calibration.py`;
- пересчитать alias, legacy и architecture inventories;
- обновить документы фактического состояния;
- не менять runtime behavior, callbacks, команды, SQL и пользовательские тексты.

### Критерии готовности

- handler alias count уменьшается с 46 до 44;
- все 44 оставшихся aliases имеют repository references;
- отсутствуют references на удалённые aliases;
- production legacy-consumer baseline остаётся `0 / 0 / 0`;
- полный test suite, Docker build и project notes contract проходят.

### Риски и ограничения

Срез удаляет только два import facade без внутренних repository consumers. Канонические модули и runtime registration не изменяются.

## После завершения

### Фактически сделано

- удалены `velvet_bot/handlers/ai_jobs.py` и `velvet_bot/handlers/quality_calibration.py`;
- количество handler aliases уменьшено с 46 до 44;
- все 44 оставшихся aliases имеют repository references;
- references на отсутствующие aliases: 0;
- production legacy-consumer baseline сохранён на `0 / 0 / 0`;
- quality-controller compatibility test теперь разделяет canonical controllers и реально оставшиеся aliases;
- документы и три machine inventories синхронизированы с текущим деревом.

### Миграции и совместимость

Миграции не требуются. Удалены только два Python import facade без repository consumers. Канонические quality controllers, router registration, callback contracts, команды, SQL и пользовательские тексты не изменены.

### Проверки

- inventory contract suite: 9 tests + 25 subtests, success;
- alias, legacy и architecture inventory checks: success;
- целевой regression/inventory suite: 21 tests + 4062 subtests, success;
- полный локальный suite: 924 tests, success; 24 PostgreSQL integration tests skipped без `TEST_DATABASE_URL`; 4775 subtests, success;
- финальные GitHub Actions фиксируются на head PR.

### PR и commit

- PR: создаётся после полного локального прогона;
- ветка: `agent/p3d-zero-reference-alias-retirement`;
- локальное verified tree готово к публикации отдельным squash PR.

### Незавершённое

Остаются 44 handler aliases, все с repository references, 8 runtime compatibility components, 114 root modules и неоднородное размещение repositories.

### Следующий шаг

Мигрировать следующую связанную alias-группу character/story либо analytics/core. После сокращения compatibility-слоя перейти к P3E repository/root module layout и duplicate helper inventory.
