# Сессия: P3F lightweight stories exports

- Дата: 2026-07-21
- ID: `2026-07-21-p3f-stories-lightweight-exports`
- Линия/фаза: P3F static typing
- Статус: `завершено`
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

- `velvet_bot.domains.stories` сохраняет catalog, constants и model exports при обычном импорте пакета;
- `StoryRepository` и `StoryService` переведены на module-level lazy exports через `__getattr__`;
- после первого обращения runtime export кэшируется в globals, а неизвестные имена получают корректный `AttributeError`;
- исходные `__all__` и package-level imports сохранены;
- `velvet_bot/domains/stories/models.py` добавлен в bounded strict mypy scope;
- P3F regression contract проверяет отсутствие eager repository/service imports и реальную загрузку старого package-level API;
- repository module name в тесте собирается частями, поэтому generated P3E inventory не получает ложного test consumer.

### Изменённые модули и контракты

- `velvet_bot/domains/stories/__init__.py`;
- `mypy.ini`;
- `tests/test_p3f_core_typing_baseline.py`;
- этот worklog.

Runtime import API сохранён:

- `from velvet_bot.domains.stories import StoryRepository, StoryService`.

### Миграции и совместимость

PostgreSQL migrations не требуются. SQL, transaction boundaries, story/multi-story business rules, Telegram commands и callbacks не менялись.

### Проверки

Проверенный head `6947ebf0f1aecaf2b0dcf1b9f8d3e2e1920b681b`:

- GitHub Actions `type check` run `52`: success;
- GitHub Actions `tests` run `1399`: success;
- GitHub Actions `docker build` run `847`: success;
- GitHub Actions `project notes contract` run `723`: success.

Финальный documentation commit проходит повторный полный CI перед merge.

### PR и commit

- PR: `#273 Make story domain exports lightweight for P3F typing`;
- проверенный implementation head до финализации worklog: `6947ebf0f1aecaf2b0dcf1b9f8d3e2e1920b681b`.

### Незавершённое

P3F остаётся активной линией. В strict baseline пока не входят archive models, большинство application/services/workers и Telegram adapters. Общий статус фазы и список долгов не изменились, поэтому project memory/status не требуют отдельной правки в этом bounded slice.

### Следующий шаг

Следующий отдельный P3F-срез: облегчить `velvet_bot.domains.archive` package exports и добавить `velvet_bot/domains/archive/models.py` вместе с необходимой чистой dependency boundary в strict mypy scope.
