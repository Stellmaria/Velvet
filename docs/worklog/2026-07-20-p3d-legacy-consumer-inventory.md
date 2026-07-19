# Сессия: P3D инвентарь legacy consumers

- Дата: 2026-07-20
- ID: `2026-07-20-p3d-legacy-consumer-inventory`
- Линия/фаза: Velvet Archive, P3D
- Статус: `завершено`
- Ветка: `agent/p3d-legacy-consumer-inventory`
- Базовый commit: `c198db0582cb24c6bbd34ed14b5a3dfd2231f741`

## Перед началом

### Цель

Добавить машинный инвентарь production consumers старых `velvet_bot.handlers.*` путей, запретить появление новых legacy imports и очистить character/story profile controllers от зависимости на приватные helpers legacy-модуля.

### Исходный контекст

P3C завершён: 68 файлов `velvet_bot/handlers/*.py` являются временными module aliases, активных implementations среди них нет. При этом отдельные production controllers продолжают импортировать старые пути и приватные `_profile_*` helpers, поэтому aliases пока нельзя безопасно удалять.

### Планируемый объём

- добавить AST-инвентарь legacy handler consumers;
- зафиксировать baseline и CI-проверку отсутствия новых consumers;
- вынести character profile text/keyboard в публичный presentation module;
- перевести `characters/uncategorized.py` и `stories/management.py` на canonical imports;
- обновить architecture inventory и документы фактического состояния;
- не менять callbacks, команды, SQL и пользовательское поведение.

### Критерии готовности

- production legacy consumers измеряются отдельным JSON/Markdown inventory;
- очищенные controllers не импортируют `velvet_bot.handlers` и приватные helpers другого controller;
- profile rendering используется через публичный presentation contract;
- число legacy consumers уменьшается и новые imports блокируются тестом;
- tests, Docker build и project notes contract проходят.

### Риски и ограничения

Module aliases нельзя удалять до нулевого consumer inventory. Физическая очистка imports не смешивается с изменением поведения, callback prefixes или persistence. GitHub code search может показывать устаревшие snapshots, поэтому источником истины является AST текущего checkout в CI.

## После завершения

### Фактически сделано

- добавлен AST-инвентарь production imports и dynamic references на `velvet_bot.handlers.*`;
- создан baseline: 20 consumer-файлов, 30 references, 18 legacy modules;
- очищены `characters/uncategorized.py` и `stories/management.py`;
- `AdminDirectoryCallback` вынесен в публичный character contract с compatibility export из `directory.py`;
- profile text и keyboard вынесены в `characters/profile_views.py`;
- старые `_profile_text` и `_profile_keyboard` оставлены в `directory.py` только как временные wrappers для ещё не перенесённых consumers;
- обновлены project memory, development status, architecture audit и changelog;
- временный source snapshot workflow и patch payload удалены до финализации ветки.

### Миграции и совместимость

Миграции не требуются. Callback prefix `adir`, команды, SQL и пользовательские тексты сохранены. Все 68 старых handler aliases остаются доступными; этот срез уменьшает consumers, но ещё не удаляет aliases.

### Проверки

- target regression suite: 29 tests, success;
- полный локальный suite без PostgreSQL: 938 tests, 24 integration skips, единственный промежуточный failure был ожидаемым из-за статуса worklog `в работе`;
- `compileall`, inventory `--check` и `git diff --check`: success;
- финальные GitHub Actions запускаются на пользовательском documentation head PR #220.

### PR и commit

- PR: #220 `P3D: inventory legacy handler consumers`;
- ветка: `agent/p3d-legacy-consumer-inventory`;
- проверенный кодовый commit: `6f7379e372da27f1eb832f02855e7cbc15162b25`;
- финальный documentation head создаётся этой записью для штатного запуска GitHub Actions.

### Незавершённое

Остаются 20 production consumers, 30 references, 18 legacy modules, 68 handler aliases и 8 runtime compatibility components. Alias удаляется только после нулевого consumer count для соответствующего старого path.

### Следующий шаг

Очистить `stories/multi_story_kr.py` от `handlers.admin_directory` и `handlers.admin_stories`, используя публичные character profile views и story callback contract.
