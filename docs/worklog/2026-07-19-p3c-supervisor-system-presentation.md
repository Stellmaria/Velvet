# Сессия: перенос Supervisor и System presentation

- Дата: 2026-07-19
- ID: `2026-07-19-p3c-supervisor-system-presentation`
- Линия/фаза: Velvet Archive, P3C
- Статус: `в работе`
- Ветка: `agent/p3c-supervisor-system-presentation`
- Базовый commit: `37cf584d07972f88236b30a718222192e4a12bf8`

## Перед началом

### Цель

Перенести первый связный набор активных Telegram controllers из legacy `velvet_bot/handlers` в канонический `velvet_bot/presentation/telegram/routers`, сохранив команды, callback contracts, порядок регистрации и старые import paths.

### Исходный контекст

P3A–P3B создали ordered router bundles и машинный layout inventory. Текущий остаток: 68 legacy handler-файлов, 110 корневых модулей и 8 active compatibility components. Следующим измеримым срезом выбран Supervisor/System, поскольку эти контроллеры уже логически разделены и имеют собственные application/transport boundaries.

### Планируемый объём

- перенести `system_center.py` и Supervisor controller family в presentation package;
- заменить старые handler-файлы тонкими re-export facades;
- перевести router bundle и внутренние imports на канонические пути;
- адаптировать архитектурные тесты и inventories;
- не менять callbacks, команды, тексты, HTTP client и Supervisor semantics.

### Критерии готовности

- canonical Supervisor/System modules содержат реальную реализацию;
- старые `velvet_bot.handlers.supervisor_*` и `system_center` не содержат decorators или business logic;
- существующие imports через старые пути продолжают работать;
- command/callback inventories не меняются;
- legacy handler implementation count уменьшается измеримо;
- полный CI зелёный.

### Риски и ограничения

Физический перенос способен нарушить import order, monkeypatch target или тесты, читающие конкретные пути. Поэтому старые модули сохраняются как lazy facades, а поведение не рефакторится одновременно с перемещением.

## После завершения

### Фактически сделано

Заполняется после реализации.

### Миграции и совместимость

Миграции PostgreSQL не планируются.

### Проверки

Заполняется после CI.

### PR и commit

Заполняется после создания PR.

### Незавершённое

Заполняется после реализации.

### Следующий шаг

Заполняется после реализации.
