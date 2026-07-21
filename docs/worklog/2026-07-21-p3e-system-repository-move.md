# Сессия: P3E system repository infrastructure move

- Дата: 2026-07-21
- ID: `2026-07-21-p3e-system-repository-move`
- Линия/фаза: P3E repository and root-module layout
- Статус: `завершено`
- Ветка: `agent/p3e-move-system-repository`
- Базовый commit: `cb09f9ef0386bc4d0afc3e0e7449c2b6d23344a9`

## Перед началом

### Цель

Перенести последний central repository из общего `velvet_bot.repositories` в каноническую PostgreSQL infrastructure boundary, удалить опустевший central package и завершить P3E repository layout migration.

### Исходный контекст

После устранения всех корневых `*_repository.py` baseline составлял 31 repository-модуль: 30 domain, 1 central, 0 root и 0 infrastructure repositories. Единственным оставшимся кандидатом был `velvet_bot.repositories.system_repository`.

### Архитектурная классификация

`SystemRepository` использует PostgreSQL-specific функции `current_setting`, `pg_database_size` и читает диагностическую сводку сразу по миграциям, персонажам, медиа, каналам, публикациям, visual scans и backup runs. Это read-only PostgreSQL adapter для runtime diagnostics, а не самостоятельный бизнес-домен.

### Планируемый объём

- создать `velvet_bot/infrastructure/postgres/system_repository.py`;
- создать package export `velvet_bot/infrastructure/postgres/__init__.py`;
- перевести bootstrap и system-health service на canonical infrastructure import;
- перевести Phase 18Q и Phase 6 runtime tests;
- удалить `velvet_bot/repositories/system_repository.py` и пустой package `velvet_bot/repositories`;
- добавить terminal state в repository inventory;
- не менять SQL, health-check API, Telegram UI или PostgreSQL schema.

### Критерии готовности

- central repositories уменьшаются 1 → 0;
- infrastructure repositories увеличиваются 0 → 1;
- domain repositories остаются 30;
- root repositories остаются 0;
- repository module count остаётся 31;
- generated inventory имеет `candidate: null` и terminal target;
- полный CI проходит.

### Риски и ограничения

Repository агрегирует PostgreSQL diagnostics поперёк нескольких таблиц. Поэтому SQL, порядок полей snapshot, mapping значений и public health-check contract не изменяются. Срез меняет только физическое расположение и import paths.

## После завершения

### Фактически сделано

- `SystemRepository` и `RuntimeDatabaseSnapshot` перенесены в `velvet_bot.infrastructure.postgres.system_repository`;
- bootstrap, system-health service и оба boundary tests переведены на canonical import;
- старый central implementation и `velvet_bot/repositories/__init__.py` удалены;
- generated inventory фиксирует 30 domain и 1 infrastructure repository;
- root и central repository counts равны нулю;
- inventory generator получил явное состояние `repository layout migration complete`;
- regression contract запрещает возврат старых root и central paths.

### Миграции и совместимость

PostgreSQL migrations не требуются. SQL runtime snapshot, mapping, health-check lifecycle и пользовательский system UI не менялись. Исторический import `velvet_bot.repositories.system_repository` удалён без compatibility facade после миграции всех известных consumers.

### Проверки

Полный GitHub CI проверяет unit/integration contracts, Docker build и project notes. Дополнительно Phase 18Q подтверждает public `Database.acquire()`, Phase 6 runtime проверяет system-health behavior, а generated inventory contract фиксирует завершённую P3E-структуру.

### PR и commit

PR: `#260 Complete P3E repository layout migration`. Итоговый merge commit фиксируется после полного зелёного CI.

### Итог P3E

- repository modules: 31;
- domain: 30;
- infrastructure: 1;
- central: 0;
- root: 0;
- root Python modules: 110;
- следующий repository candidate: отсутствует.

### Незавершённое

В рамках P3E незавершённых repository-layout срезов нет. Отдельно остаются P3F gradual static typing, inventory общих Telegram helpers и operational verification на Windows/staging.

### Следующий шаг

После синхронизации status-документов перейти к P3F gradual static typing baseline. Отдельно продолжить inventory общих Telegram helpers и duplicate code, не смешивая типизацию с изменением runtime behavior.
