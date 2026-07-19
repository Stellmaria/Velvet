# Сессия: организация оставшейся архитектуры P3

- Дата: 2026-07-19
- ID: `2026-07-19-p3-architecture-organization`
- Линия/фаза: Velvet Archive, P3A–P3D
- Статус: `частично`
- Ветка: `agent/p3-architecture-organization`
- Базовый commit: `3d98a60a49e5d3212be218cd7b0af705a1a06a2b`

## Перед началом

### Цель

Синхронизировать архитектурные источники истины после закрытия P2, уменьшить связанность корневого Telegram Router, оформить активные compatibility-слои как явную границу и создать измеримый следующий план физического переноса presentation-контроллеров.

### Исходный контекст

Фазы 7, 9–10, 12–18 и P2 завершены. Private PostgreSQL boundary равна 0/0, P2 stability inventory равна 67 approved / 0 unresolved и late/missing callback равны 0. При этом `presentation/telegram/router.py` напрямую импортировал десятки модулей из `velvet_bot.handlers`, активные compatibility installers вызывались разрозненно, а `project_memory`, `development_status`, `ARCHITECTURE_AUDIT` и `CHANGELOG` описывали состояние до PR #193.

### Планируемый объём

- обновить источники истины до фактического состояния `main`;
- вынести регистрацию Telegram routers в доменные bundles;
- оставить в root router только крупные группы и глобальный error boundary;
- централизовать pre-import и post-import compatibility installers;
- добавить архитектурные regression-тесты;
- зафиксировать внешние эксплуатационные обязательства отдельно от кодового долга.

### Критерии готовности

- root router не импортирует `velvet_bot.handlers` напрямую;
- порядок publication-before-archive и остальных catch-all-sensitive routers сохранён;
- активные compatibility installers перечислены в одном модуле и имеют явные стадии;
- документы отражают P2 67/67, private pool 0/0 и фактический остаток P3;
- полный CI зелёный.

### Риски и ограничения

Массовый физический перенос всех handler-файлов одним PR запрещён: он создаёт трудно проверяемый diff и повышает риск изменения порядка aiogram routers. Этот срез меняет только composition и документацию, не callback prefixes, команды, SQL, use cases или бизнес-поведение. Живые Windows, staging и offsite операции требуют внешних токенов, базы, хранилища и запуска на целевой машине, поэтому могут быть подготовлены кодом и runbook, но не объявлены фактически выполненными без такой проверки.

## После завершения

### Фактически сделано

- root Telegram Router сокращён до четырёх ordered domain bundles;
- 55 активных handler imports распределены по bundles без дублей;
- publication Router сохранён перед archive catch-all;
- активные compatibility installers собраны в единый pre-import/post-import registry;
- package-level side effects удалены из `handlers/__init__.py`;
- неиспользуемый discussion dashboard compatibility bridge удалён;
- добавлены AST regression-тесты для root composition, bundle coverage, порядка и compatibility registry;
- добавлен генератор `architecture_layout_inventory` и CI-проверка его актуальности;
- сгенерированный inventory фиксирует 0 прямых handler imports в root, 55 активных registrations без дублей, 68 legacy handler-файлов, 110 root modules и 8 active compatibility components;
- обновлены `development_status`, `project_memory`, `ARCHITECTURE_AUDIT`, README и CHANGELOG;
- временный generator workflow удалён после фиксации результата.

### Миграции и совместимость

Миграции PostgreSQL не требуются. Callback prefixes, команды, use cases, SQL и бизнес-поведение не менялись. Исторический `handlers.router` import сохранён как lazy compatibility export без startup side effects.

### Проверки

- одноразовый architecture generator run #1: success;
- clean tests, Docker build и project notes contract выполняются на итоговой ветке;
- первый project notes run выявил ожидаемый незавершённый статус worklog и обязательные compatibility headings, оба контракта исправлены.

### PR и commit

- PR: #194 `Organize remaining P3 architecture boundaries`;
- текущая ветка: `agent/p3-architecture-organization`;
- итоговый merge commit будет добавлен после зелёного CI.

### Незавершённое

В этом срезе не выполняется массовый физический перенос 68 legacy handler-файлов и 110 корневых модулей. Не закрываются внешние операции, требующие токена staging-бота, staging-базы, offsite-хранилища либо живого запуска на Windows. Эти пункты остаются отдельными P3C–P3F и эксплуатационными срезами.

### Следующий шаг

После зелёного CI завершить запись и слить PR #194. Затем начать P3C с физического переноса Supervisor/system presentation controllers через канонические модули и временные handler re-exports.
