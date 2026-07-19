# Сессия: перенос Supervisor и System presentation

- Дата: 2026-07-19
- ID: `2026-07-19-p3c-supervisor-system-presentation`
- Линия/фаза: Velvet Archive, P3C
- Статус: `частично`
- Ветка: `agent/p3c-supervisor-system-presentation`
- Базовый commit: `37cf584d07972f88236b30a718222192e4a12bf8`

## Перед началом

### Цель

Перенести первый связный набор активных Telegram controllers из legacy `velvet_bot/handlers` в канонический `velvet_bot/presentation/telegram/routers`, сохранив команды, callback contracts, порядок регистрации и старые import paths.

### Исходный контекст

P3A–P3B создали ordered router bundles и машинный layout inventory. Исходный остаток: 68 legacy handler-файлов, 110 корневых модулей и 8 active compatibility components. Следующим измеримым срезом выбран Supervisor/System, поскольку эти контроллеры уже логически разделены и имеют собственные application/transport boundaries.

### Планируемый объём

- перенести `system_center.py` и Supervisor controller family в presentation package;
- заменить старые handler-файлы тонкими module-alias facades;
- перевести router bundle и production imports на канонические пути;
- адаптировать архитектурные тесты и inventories;
- не менять callbacks, команды, тексты, HTTP client и Supervisor semantics.

### Критерии готовности

- canonical Supervisor/System modules содержат реальную реализацию;
- старые `velvet_bot.handlers.supervisor_*` и `system_center` не содержат decorators или business logic;
- существующие imports и monkeypatch targets через старые пути продолжают работать;
- command/callback inventories не меняются;
- legacy handler implementation count уменьшается измеримо;
- полный CI зелёный.

### Риски и ограничения

Физический перенос способен нарушить import order, monkeypatch target или тесты, читающие конкретные пути. Поэтому старые модули сохраняются как aliases того же module object, а поведение не рефакторится одновременно с перемещением.

## После завершения

### Фактически сделано

- восемь Supervisor controllers перенесены в `velvet_bot/presentation/telegram/routers/supervisor/`;
- `system_center.py` перенесён в `velvet_bot/presentation/telegram/routers/system.py`;
- старые девять handler paths заменены короткими module aliases через `sys.modules`, поэтому старый и канонический import возвращают один объект;
- `core_operations.py` и owner menu используют канонические Supervisor/System paths;
- Supervisor composition переведён на канонические дочерние controllers;
- добавлены module-identity, alias-size, canonical ownership и active-composition regression-тесты;
- phase 10 architecture contracts переведены на канонические пути;
- layout inventory разделяет физические legacy-файлы, активные implementations и временные aliases;
- активные legacy handler implementations уменьшены с 68 до 59;
- временный move-workflow удалён после pre-execution failure, перенос выполнен атомарным Git tree commit.

### Миграции и совместимость

Миграции PostgreSQL не требуются. Команды, callback prefixes, тексты, application use cases, Supervisor HTTP API и system semantics не менялись. Девять старых import paths сохранены как полные module aliases для обратной совместимости и корректной работы `unittest.mock.patch`.

### Проверки

- статическая сверка PR diff и import graph выполнена;
- architecture inventory: root imports 0, active routers 55, duplicates 0, implementations 59, aliases 9;
- GitHub Actions tests #933, Docker #469 и notes #334, а также последующие попытки, завершились до первого workflow step с `steps=None`, `logs_url=None` и без checkout;
- повторный запуск unit-tests также завершился до первого шага и не создал log blob;
- точная причина pre-execution failure недоступна подключённому GitHub integration API, поэтому обязательный реальный CI пока не выполнен.

### PR и commit

- PR: #195 `Move Supervisor and System controllers into presentation`;
- атомарный move commit: `5ad5431929e29fc552fef0d38222f8b9082c3200`;
- ветка: `agent/p3c-supervisor-system-presentation`.

### Незавершённое

PR не готов к слиянию до первого фактического запуска tests, Docker build и project notes contract. Следующие presentation-домены, root modules и active compatibility components остаются отдельными P3-срезами.

### Следующий шаг

После восстановления выполнения GitHub Actions или доступного локального checkout выполнить полный CI, исправить реальные регрессии при наличии, завершить worklog и слить PR #195. Затем перенести characters/stories controllers.
