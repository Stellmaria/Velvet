# Сессия: P3F lightweight archive exports

- Дата: 2026-07-21
- ID: `2026-07-21-p3f-archive-lightweight-exports`
- Линия/фаза: P3F static typing
- Статус: `частично`
- Ветка: `agent/p3f-archive-lightweight-exports`
- Базовый commit: `af48ae907bb066f77fa4a83556c6a794b9c60854`

## Перед началом

### Цель

Сделать `velvet_bot.domains.archive` лёгкой package boundary и добавить archive dataclasses в bounded strict mypy baseline без затягивания repository/service/preview-persistence graph.

### Исходный контекст

Предыдущие P3F-срезы облегчили characters, references и stories package exports. `archive.models` зависит от `characters.models`, чья parent package boundary теперь не импортирует persistence eagerly. Сам archive package всё ещё eager-imports `ArchiveRepository`, `ArchivePreviewRepository` и `ArchiveService`.

### Какую существующую функцию улучшает изменение

Изменение повышает надёжность разработки существующего архива: модели карточек, медиа и preview получают строгую статическую проверку, а model-only imports перестают поднимать persistence/service modules.

### Что станет проще и надёжнее

- archive и preview dataclasses войдут в защищённый typing baseline;
- импорт моделей архива станет легче и предсказуемее;
- package-level repository/service imports сохранят runtime compatibility;
- regression contract заблокирует возврат eager persistence imports.

### Почему это не новая предметная область

Архивные команды, публичный архив, preview processing, SQL, migrations, watermark и Telegram delivery не меняются. Это внутренний architecture/tooling slice существующего домена.

### Планируемый объём

- заменить eager archive repository/service exports на lazy runtime exports;
- сохранить `__all__` и package-level import API;
- добавить `archive/models.py` и `archive/preview_models.py` в `mypy.ini`;
- расширить P3F regression test;
- выполнить полный CI и завершить worklog.

### Критерии готовности

- `archive.__init__` не содержит static imports repository/service/preview_repository;
- package-level repository/service imports работают;
- strict mypy scope включает archive и preview models;
- generated inventories не получают ложных consumers;
- tests, type check, Docker и project notes зелёные.

### Риски и ограничения

- package экспортирует три runtime persistence/service класса вместо двух, поэтому mapping и compatibility assertions должны охватить все три;
- archive models зависят от characters models, но уже очищенная characters boundary должна удержать scope bounded;
- runtime behavior и PostgreSQL schema не меняются.

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

После завершения провести inventory первого transport-neutral application/service scope вместо механического расширения только на model files.
