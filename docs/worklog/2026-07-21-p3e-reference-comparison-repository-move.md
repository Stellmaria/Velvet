# Сессия: P3E reference comparison repository move

- Дата: 2026-07-21
- ID: `2026-07-21-p3e-reference-comparison-repository-move`
- Линия/фаза: P3E repository and root-module layout
- Статус: `завершено`
- Ветка: `agent/p3e-move-reference-comparison-repository`
- Базовый commit: `07c3cace61dda3a5c693b220727b142a04b09b44`

## Перед началом

### Цель

Перенести persistence AI-сравнения результата с референсом из корня `velvet_bot` в домен `velvet_bot.domains.references`, перевести production controller и Phase 18 boundary contract на canonical import и удалить старый root path.

### Исходный контекст

После предыдущих P3E-срезов repository baseline составлял 31 модуль: 27 domain, 1 central и 3 root repositories. `velvet_bot.reference_comparison_repository` имел одного production consumer, одного test consumer и не имел package exports.

### Планируемый объём

- создать `velvet_bot/domains/references/comparison_repository.py`;
- сохранить implementation и SQL без логических изменений;
- перевести Telegram reference-comparison controller на domain import;
- перевести Phase 18 public-acquire contract на canonical module;
- удалить старый root repository;
- обновить repository и architecture inventories;
- не менять команды, AI prompt, формат отчёта и PostgreSQL schema.

### Критерии готовности

- старый root module отсутствует;
- canonical domain module используется controller и Phase 18 test;
- repository count остаётся 31;
- domain repositories увеличиваются 27 → 28;
- root repositories уменьшаются 3 → 2;
- root Python modules уменьшаются 113 → 112;
- полный CI проходит.

### Риски и ограничения

Repository сохраняет JSONB AI-отчёт и отдельные score-поля. Поэтому состав INSERT, порядок параметров, ограничения строк provider/model, JSON serialization и возвращаемый report id не изменяются. Срез меняет только физическое расположение и import paths.

## После завершения

### Фактически сделано

- implementation перенесён в `velvet_bot.domains.references.comparison_repository`;
- Telegram controller переведён на canonical import;
- Phase 18 completion contract переведён на domain module;
- старый `velvet_bot/reference_comparison_repository.py` удалён;
- P3E regression contract фиксирует отсутствие root path и наличие canonical domain path;
- generated inventories синхронизированы.

### Миграции и совместимость

PostgreSQL migrations не требуются. Исторический import `velvet_bot.reference_comparison_repository` удалён. Telegram command contract, AI comparison workflow и структура сохраняемого отчёта остаются прежними.

### Проверки

Полный GitHub CI проверяет unit/integration contracts, Docker build, project notes и generated inventories. Phase 18 contract дополнительно подтверждает использование public `Database.acquire()` и отсутствие `_require_pool`.

### PR и commit

PR создаётся из ветки `agent/p3e-move-reference-comparison-repository`; итоговый merge commit фиксируется после зелёного CI.

### Незавершённое

После среза остаются 2 root repositories и один central `system_repository`.

### Следующий шаг

Перенести `velvet_bot.media_set_actions_repository` в `velvet_bot.domains.media_sets` отдельным P3E-срезом после проверки его production service и repository-specific tests.
