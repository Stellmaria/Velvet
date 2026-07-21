# Сессия: P3E media set duplicate repository move

- Дата: 2026-07-21
- ID: `2026-07-21-p3e-media-set-duplicate-repository-move`
- Линия/фаза: P3E repository and root-module layout
- Статус: `завершено`
- Ветка: `agent/p3e-move-media-set-duplicate-repository`
- Базовый commit: `129e43a5a06278dbee29719d929b01331861c0f6`

## Перед началом

### Цель

Перенести `MediaSetDuplicateActionsRepository` из корня `velvet_bot` в уже созданный домен `velvet_bot.domains.media_sets`, перевести production и architectural-test consumers на canonical import и удалить старый root path без compatibility facade.

### Исходный контекст

После первых P3E-срезов repository baseline составлял 31 модуль: 24 domain, 1 central и 6 root repositories. `velvet_bot.media_set_duplicate_actions_repository` был первым кандидатом с одним production consumer, одним test consumer и без package exports.

### Планируемый объём

- создать `velvet_bot/domains/media_sets/duplicate_actions_repository.py`;
- сохранить implementation и SQL без логических изменений;
- экспортировать repository из domain package;
- перевести `media_set_duplicate_actions.py` на domain import;
- перевести Phase 18 boundary contract на canonical module;
- удалить старый root repository;
- обновить repository и architecture inventories;
- не менять Telegram callbacks, media-set workflow и PostgreSQL schema.

### Критерии готовности

- старый root module отсутствует;
- domain implementation импортируется и используется production service;
- Phase 18 public-acquire contract проверяет canonical module;
- repository count остаётся 31;
- domain repositories увеличиваются 24 → 25;
- root repositories уменьшаются 6 → 5;
- root Python modules уменьшаются 116 → 115;
- полный CI проходит.

### Риски и ограничения

Repository выполняет транзакционное создание media-set candidate из duplicate candidate. Поэтому SQL, порядок блокировок, conflict handling, очистка пересекающихся candidates и финальный duplicate status не изменяются. Срез меняет только физическое расположение и import paths.

## После завершения

### Фактически сделано

- implementation перенесён в `velvet_bot.domains.media_sets.duplicate_actions_repository` без изменения SQL;
- `MediaSetDuplicateActionsRepository` добавлен в exports домена;
- production compatibility service переведён на domain import;
- Phase 18 completion contract переведён на canonical module;
- старый `velvet_bot/media_set_duplicate_actions_repository.py` удалён;
- P3E regression contract фиксирует отсутствие root path и наличие domain path;
- generated inventories синхронизированы.

### Миграции и совместимость

PostgreSQL migrations не требуются. Исторический import `velvet_bot.media_set_duplicate_actions_repository` удалён. Runtime API функции `create_set_candidate_from_duplicate` и installer contract остаются прежними.

### Проверки

Полный GitHub CI проверяет unit/integration contracts, Docker build, project notes и generated inventories. Phase 18 contract дополнительно подтверждает использование public `Database.acquire()` и отсутствие `_require_pool`.

### PR и commit

PR создаётся из ветки `agent/p3e-move-media-set-duplicate-repository`; итоговый merge commit фиксируется после зелёного CI.

### Незавершённое

После среза остаются 5 root repositories и один central `system_repository`. Следующий измеримый кандидат: `velvet_bot.quality_set_ai_repository`.

### Следующий шаг

Перенести `quality_set_ai_repository` в канонический quality/media-quality domain отдельным P3E-срезом после проверки его production controller и тестовых contracts.
