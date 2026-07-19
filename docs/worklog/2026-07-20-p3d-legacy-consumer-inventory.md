# Сессия: P3D инвентарь legacy consumers

- Дата: 2026-07-20
- ID: `2026-07-20-p3d-legacy-consumer-inventory`
- Линия/фаза: Velvet Archive, P3D
- Статус: `в работе`
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

В работе.

### Миграции и совместимость

Миграции не требуются. Старые import paths сохраняются.

### Проверки

Будут зафиксированы после выполнения.

### PR и commit

Будут зафиксированы после выполнения.

### Незавершённое

Будет уточнено после инвентаризации.

### Следующий шаг

Перейти к следующей связной группе legacy consumers после подтверждения baseline.
