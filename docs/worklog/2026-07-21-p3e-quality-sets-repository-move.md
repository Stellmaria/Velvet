# Сессия: P3E media set quality repository move

- Дата: 2026-07-21
- ID: `2026-07-21-p3e-quality-sets-repository-move`
- Линия/фаза: P3E repository and root-module layout
- Статус: `завершено`
- Ветка: `agent/p3e-move-quality-sets-repository`
- Базовый commit: `1f41208bc7ea4070c15c49a1300d4d8430e7d21c`

## Перед началом

### Цель

Перенести две persistence-операции quality-set workflow из корневого `quality_sets_repository.py` в домен `velvet_bot.domains.media_sets`, перевести Telegram controller и Phase 18 contract на canonical import и удалить старый root path.

### Исходный контекст

После переноса media-set AI repository baseline составлял 31 модуль: 26 domain, 1 central и 4 root repositories. `velvet_bot.quality_sets_repository` был первым кандидатом с одним production consumer и одним test consumer.

### Планируемый объём

- создать `velvet_bot/domains/media_sets/quality_repository.py`;
- сохранить SQL и нормализацию AI error без изменений;
- перевести quality-sets Telegram controller на canonical import;
- перевести Phase 18 public-acquire contract;
- удалить старый root repository;
- обновить P3E и architecture inventories;
- не менять callbacks, candidate decisions и Qwen workflow.

### Критерии готовности

- old root module отсутствует;
- controller и Phase 18 используют domain module;
- repository count остаётся 31;
- domain repositories увеличиваются 26 → 27;
- root repositories уменьшаются 4 → 3;
- root Python modules уменьшаются 114 → 113;
- полный CI проходит.

### Риски и ограничения

Срез сохраняет SQL для скрытия filename/context fallback candidates и запрос последней AI error. Условия status, reason marker, сортировка и ограничение error text до 600 символов не меняются.

## После завершения

### Фактически сделано

- implementation перемещён в `velvet_bot.domains.media_sets.quality_repository`;
- Telegram quality-sets controller переведён на canonical domain import;
- Phase 18 completion contract переведён на новый module;
- старый `velvet_bot/quality_sets_repository.py` удалён;
- P3E regression contract фиксирует отсутствие root path и наличие domain path;
- generated repository и architecture inventories синхронизированы.

### Миграции и совместимость

PostgreSQL migrations не требуются. Исторический import `velvet_bot.quality_sets_repository` удалён. Callback schema, public controller behavior и database tables остаются прежними.

### Проверки

Полный GitHub CI проверяет tests, Docker build, project notes и generated inventories. Phase 18 contract подтверждает два использования public `Database.acquire()`.

### PR и commit

PR создаётся из ветки `agent/p3e-move-quality-sets-repository`; итоговый merge commit фиксируется после зелёного CI.

### Незавершённое

После среза остаются 3 root repositories и один central `system_repository`. Следующий кандидат: `velvet_bot.reference_comparison_repository`.

### Следующий шаг

Перенести reference comparison persistence в домен `references`, сохранив SQL и Telegram comparison controller behavior.
