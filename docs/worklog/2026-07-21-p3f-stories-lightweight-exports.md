# Сессия: P3F lightweight stories exports

- Дата: 2026-07-21
- ID: `2026-07-21-p3f-stories-lightweight-exports`
- Линия/фаза: P3F static typing
- Статус: `частично`
- Ветка: `agent/p3f-stories-lightweight-exports`
- Базовый commit: `fcc9757fafdd75b23a21e909db1223577ddcf672`

## Перед началом

### Цель

Сделать `velvet_bot.domains.stories` лёгкой package boundary и добавить `velvet_bot/domains/stories/models.py` в bounded strict mypy baseline без затягивания story repository/service graph.

### Исходный контекст

Предыдущий P3F-срез добавил reference models и доказал pattern lazy runtime exports для persistence/service API. Story models состоят из dataclasses и `datetime.date`, не используют Telegram, SQL, asyncpg или network clients, но `stories.__init__` eager-imports `StoryRepository` и `StoryService`.

### Какую существующую функцию улучшает изменение

Изменение повышает надёжность разработки существующего контура историй: model contracts получают strict static checking, а model-only import перестаёт загружать persistence/service modules.

### Что станет проще и надёжнее

- story dataclasses войдут в защищённый typing baseline;
- package initialization станет легче;
- package-level `StoryRepository`/`StoryService` imports сохранят runtime compatibility;
- regression contract запретит возврат eager persistence imports.

### Почему это не новая предметная область

Команды историй, multi-story UI, SQL, migrations и business rules не меняются. Это внутренний architecture/tooling slice существующего домена.

### Планируемый объём

- заменить eager story repository/service exports на lazy runtime exports;
- сохранить `__all__` и package-level import API;
- добавить stories models в `mypy.ini`;
- расширить P3F regression test;
- выполнить полный CI и завершить worklog.

### Критерии готовности

- `stories.__init__` не содержит static repository/service imports;
- package-level `StoryRepository` и `StoryService` работают;
- strict mypy scope включает stories models;
- generated inventories не изменяются случайно;
- tests, type check, Docker и project notes зелёные.

### Риски и ограничения

- exact repository module literals в tests могут попасть в P3E inventory, поэтому test contract обязан строить их без цельной AST-константы;
- dynamic exports не должны скрывать неизвестные атрибуты;
- runtime behavior не меняется.

## После завершения

### Фактически сделано

Ожидает реализации и CI.

### Изменённые модули и контракты

Ожидает реализации.

### Миграции и совместимость

PostgreSQL migrations не планируются.

### Проверки

Ожидают выполнения.

### PR и commit

Ожидает создания PR.

### Незавершённое

Реализация, CI и итоговая запись.

### Следующий шаг

После завершения выбрать archive models либо первый application/service scope на основании отдельного mypy inventory.
