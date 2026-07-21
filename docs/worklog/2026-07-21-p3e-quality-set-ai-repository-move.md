# Сессия: P3E media set AI repository move

- Дата: 2026-07-21
- ID: `2026-07-21-p3e-quality-set-ai-repository-move`
- Линия/фаза: P3E repository and root-module layout
- Статус: `завершено`
- Ветка: `agent/p3e-move-quality-set-ai-repository`
- Базовый commit: `96df53647bea9f57e4c4e76e2a147a87d2eb57bb`

## Перед началом

### Цель

Перенести persistence AI-отчётов медиасетов из корневого `quality_set_ai_repository.py` в домен `velvet_bot.domains.media_sets`, перевести Telegram controller и Phase 18 contract на canonical import и удалить старый root path.

### Исходный контекст

После предыдущего P3E-среза baseline составлял 31 repository-модуль: 25 domain, 1 central и 5 root repositories. `velvet_bot.quality_set_ai_repository` был первым кандидатом с одним production consumer и одним test consumer.

### Планируемый объём

- создать `velvet_bot/domains/media_sets/ai_repository.py`;
- сохранить dataclasses, SQL и JSONB parsing без изменений;
- экспортировать public models из domain package;
- перевести quality-set AI Telegram controller на canonical repository;
- перевести Phase 18 public-acquire contract;
- удалить старый root repository;
- обновить P3E и architecture inventories;
- не менять AI prompts, callbacks, report schema и Telegram formatting.

### Критерии готовности

- old root module отсутствует;
- controller использует domain import;
- Phase 18 contract проверяет canonical module;
- repository count остаётся 31;
- domain repositories увеличиваются 25 → 26;
- root repositories уменьшаются 5 → 4;
- root Python modules уменьшаются 115 → 114;
- полный CI проходит.

### Риски и ограничения

Repository содержит четыре persistence boundary: загрузка набора, пагинация наборов, чтение последнего JSONB-отчёта и сохранение отчёта. SQL, LIMIT, page-size bounds, JSON decoding и сериализация отчёта не изменяются.

## После завершения

### Фактически сделано

- implementation перемещён в `velvet_bot.domains.media_sets.ai_repository` без изменения логики;
- public report models экспортируются из `velvet_bot.domains.media_sets`;
- Telegram quality-set AI controller переведён на canonical domain import;
- Phase 18 completion contract переведён на новый module;
- старый `velvet_bot/quality_set_ai_repository.py` удалён;
- P3E regression contract фиксирует отсутствие root path и наличие domain path;
- generated repository и architecture inventories синхронизированы.

### Миграции и совместимость

PostgreSQL migrations не требуются. Исторический import `velvet_bot.quality_set_ai_repository` больше не поддерживается. Команды, callback schema, AI report fields и таблица `media_set_ai_reports` остаются прежними.

### Проверки

Полный GitHub CI проверяет unit/integration tests, Docker build, project notes и generated inventories. Phase 18 contract подтверждает четыре использования public `Database.acquire()` и отсутствие private pool access.

### PR и commit

PR создаётся из ветки `agent/p3e-move-quality-set-ai-repository`; итоговый merge commit фиксируется после зелёного CI.

### Незавершённое

После среза остаются 4 root repositories и один central `system_repository`. Следующий кандидат: `velvet_bot.quality_sets_repository`.

### Следующий шаг

Перенести repository ручного управления quality-сетами в домен `media_sets`, сохраняя SQL и controller behavior.
