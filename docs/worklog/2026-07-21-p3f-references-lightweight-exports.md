# Сессия: P3F lightweight references exports

- Дата: 2026-07-21
- ID: `2026-07-21-p3f-references-lightweight-exports`
- Линия/фаза: P3F static typing
- Статус: `частично`
- Ветка: `agent/p3f-references-lightweight-exports`
- Базовый commit: `15f14b4aef818310b0eaee164149f6bbd99725c5`

## Перед началом

### Цель

Сделать пакет `velvet_bot.domains.references` лёгкой границей для анализа `models.py`, не меняя существующие runtime imports `ReferenceRepository` и `ReferenceService`, и добавить reference models в bounded strict mypy baseline.

### Исходный контекст

P3F уже проверяет core access/config, `topics.py` и `post_classification.py`. Попытка добавить domain model files затянула repository/service graph через package `__init__.py` и дала 90 сторонних ошибок. Сами reference models transport-neutral: dataclasses, datetime и character model dependency без Telegram, SQL, asyncpg или network clients.

### Какую существующую функцию улучшает изменение

Изменение улучшает разработку и сопровождение существующего контура референсов: чистые модели получают строгую статическую проверку, а пакетная граница перестаёт без необходимости загружать persistence и service modules.

### Что станет проще и надёжнее

- mypy сможет проверять reference models независимо от asyncpg/service graph;
- импорт model-only API не будет выполнять лишние repository/service imports;
- старые package-level imports repository/service сохранят runtime-совместимость;
- regression-test зафиксирует bounded scope и лёгкую package boundary.

### Почему это не новая предметная область

Пользовательские команды, Telegram callbacks, SQL, PostgreSQL schema и бизнес-правила референсов не меняются. Это внутренний architecture/tooling slice существующего домена.

### Планируемый объём

- заменить eager repository/service exports в `domains/references/__init__.py` на lazy runtime exports;
- сохранить существующий `__all__` и `from velvet_bot.domains.references import ReferenceService`;
- добавить `velvet_bot/domains/references/models.py` в strict mypy scope;
- расширить P3F regression contract;
- обновить project status/memory и итоговую запись после CI.

### Критерии готовности

- package import не содержит статических imports repository/service;
- legacy package-level repository/service imports работают во время выполнения;
- strict mypy scope включает reference models;
- `ignore_errors` и `follow_imports` не добавлены;
- full CI, type-check и project notes contract зелёные.

### Риски и ограничения

- module-level `__getattr__` должен кэшировать загруженный объект и корректно отдавать `AttributeError` для неизвестных имён;
- dynamic runtime exports намеренно не расширяют mypy scope на repository/service;
- PostgreSQL и Telegram поведение не должны измениться.

## После завершения

### Фактически сделано

Ожидает реализации и CI.

### Изменённые модули и контракты

Ожидает реализации.

### Миграции и совместимость

PostgreSQL migrations не планируются. Runtime package imports repository/service должны остаться совместимыми.

### Проверки

Ожидают выполнения в CI.

### PR и commit

Ожидает создания PR.

### Незавершённое

Реализация, CI и итоговая синхронизация документов.

### Следующий шаг

После зелёного среза применить тот же bounded boundary cleanup к `velvet_bot.domains.stories` либо `characters` на основании отдельного inventory.
