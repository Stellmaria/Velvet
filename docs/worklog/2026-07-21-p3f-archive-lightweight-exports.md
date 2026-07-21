# Сессия: P3F lightweight archive exports

- Дата: 2026-07-21
- ID: `2026-07-21-p3f-archive-lightweight-exports`
- Линия/фаза: P3F static typing
- Статус: `завершено`
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

- `velvet_bot.domains.archive` сохраняет archive и preview model exports при обычном импорте пакета;
- `ArchivePreviewRepository`, `ArchiveRepository` и `ArchiveService` переведены на module-level lazy exports через `__getattr__`;
- runtime exports кэшируются после первого обращения, остаются перечисленными в `__all__`/`__dir__` и отдают `AttributeError` для неизвестных имён;
- `velvet_bot/domains/archive/models.py` и `velvet_bot/domains/archive/preview_models.py` добавлены в bounded strict mypy scope;
- зависимость archive models от `characters.models` остаётся bounded благодаря ранее облегчённой characters package boundary;
- P3F regression contract проверяет отсутствие eager imports для archive repository, preview repository и service, а также совместимость package-level runtime imports;
- repository module names в тесте собираются частями и не создают ложные references в generated P3E inventory.

### Изменённые модули и контракты

- `velvet_bot/domains/archive/__init__.py`;
- `mypy.ini`;
- `tests/test_p3f_core_typing_baseline.py`;
- этот worklog.

Runtime import API сохранён:

- `from velvet_bot.domains.archive import ArchivePreviewRepository, ArchiveRepository, ArchiveService`.

### Миграции и совместимость

PostgreSQL migrations не требуются. SQL, transaction boundaries, preview generation/persistence, watermark, архивные и public archive Telegram scenarios не менялись.

### Проверки

Проверенный implementation head `5e46a8c807a97a32657bbf246c09c244d821ed0b`:

- GitHub Actions `type check` run `55`: success;
- GitHub Actions `tests` run `1402`: success;
- GitHub Actions `docker build` run `850`: success;
- GitHub Actions `project notes contract` run `725`: success.

Финальный documentation commit проходит повторный полный CI перед merge.

### PR и commit

- PR: `#274 Make archive domain exports lightweight for P3F typing`;
- проверенный implementation head до финализации worklog: `5e46a8c807a97a32657bbf246c09c244d821ed0b`.

### Незавершённое

P3F остаётся активной линией. Strict baseline покрывает несколько core/transport-neutral modules и модели references, stories, archive/preview, но ещё не покрывает первый полноценный application/service scope, workers и Telegram adapters. Общий статус фазы и список долгов не менялись.

### Следующий шаг

Провести отдельный inventory transport-neutral application/service modules и выбрать первый bounded scope по фактическим import dependencies, а не продолжать механически добавлять только model files.
