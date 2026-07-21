# Сессия: P3E media set AI repository move

- Дата: 2026-07-21
- ID: `2026-07-21-p3e-media-set-ai-repository-move`
- Линия/фаза: P3E repository and root-module layout
- Статус: `завершено`
- Ветка: `agent/p3e-move-media-set-ai-repository`
- Базовый commit: `1668126949c5971495c3c867c19e5deb79c4b707`

## Перед началом

### Цель

Перенести последний корневой repository, отвечающий за AI-discovery медиасетов, в домен `velvet_bot.domains.media_sets`, перевести production service и repository-specific tests на canonical import и довести root repository count до нуля.

### Исходный контекст

После предыдущих P3E-срезов repository baseline составлял 31 модуль: 29 domain, 1 central и 1 root repository. `velvet_bot.media_set_ai_repository` имел одного production consumer, один отдельный test consumer и не имел package exports.

### Планируемый объём

- создать `velvet_bot/domains/media_sets/discovery_repository.py`;
- сохранить implementation и SQL без логических изменений;
- экспортировать AI discovery models и repository из domain package;
- перевести `media_set_ai_discovery.py` на canonical import;
- перевести repository-specific tests на canonical module;
- удалить старый root repository;
- обновить repository и architecture inventories;
- не менять semantic grouping, Qwen workflow и PostgreSQL schema.

### Критерии готовности

- старый root module отсутствует;
- service и repository tests используют domain implementation;
- repository count остаётся 31;
- domain repositories увеличиваются 29 → 30;
- root repositories уменьшаются 1 → 0;
- root Python modules уменьшаются 111 → 110;
- полный CI проходит.

### Риски и ограничения

Repository загружает готовые AI-профили, ограничивает выборку, скрывает слабые fallback candidates и транзакционно upsert-ит AI candidates и их items. Поэтому SQL, limit clamp, transaction boundaries, conflict handling, inserted counter и item existence checks не изменяются.

## После завершения

### Фактически сделано

- implementation перенесён в `velvet_bot.domains.media_sets.discovery_repository`;
- AI discovery models и `MediaSetAIRepository` добавлены в exports домена;
- production AI-discovery service переведён на canonical import;
- repository-specific tests переведены на domain module;
- старый `velvet_bot/media_set_ai_repository.py` удалён;
- generated inventories и P3E regression contract синхронизированы;
- корневые `*_repository.py` устранены полностью.

### Миграции и совместимость

PostgreSQL migrations не требуются. Исторический import `velvet_bot.media_set_ai_repository` удалён. Semantic matching, fallback short circuit, candidate draft generation и discovery totals остаются прежними.

### Проверки

Полный GitHub CI проверяет unit/integration contracts, Docker build, project notes и generated inventories. Отдельный repository test подтверждает limit clamp, row mapping, retirement transaction, upserts, empty-candidate behavior и service delegation.

### PR и commit

PR создаётся из ветки `agent/p3e-move-media-set-ai-repository`; итоговый merge commit фиксируется после зелёного CI.

### Незавершённое

После среза остаётся один central repository: `velvet_bot.repositories.system_repository`.

### Следующий шаг

Классифицировать и перенести `system_repository` в каноническую system/runtime boundary отдельным P3E-срезом, обновив bootstrap, system-health service и два repository boundary tests.
