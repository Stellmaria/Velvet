# Сессия: P3F transport-neutral module baseline

- Дата: 2026-07-21
- ID: `2026-07-21-p3f-domain-models-baseline`
- Линия/фаза: P3F static typing
- Статус: `завершено`
- Ветка: `agent/p3f-domain-models-baseline`
- Базовый commit: `a16b38892b420111c7d7696fb26b0b6eca02b873`

## Перед началом

### Цель

Расширить strict mypy baseline с core на небольшой transport-neutral scope без Telegram, SQL, asyncpg и network clients.

### Исходный контекст

Первый P3F-срез уже проверяет `velvet_bot/core/access` и `velvet_bot/core/config`. Изначально следующий scope включал чистые domain model files characters/archive/references/stories.

### Планируемый объём

- расширить существующий mypy scope на несколько небольших transport-neutral modules;
- обновить regression-test baseline;
- исправить только реальные typing issues выбранного scope;
- не включать repositories, services, workers и Telegram adapters;
- не менять runtime behavior.

### Критерии готовности

- mypy strict проверяет core и новый bounded scope;
- baseline перечислен явно и защищён тестом;
- `ignore_errors`, `follow_imports=skip` и широкие suppressions отсутствуют;
- mypy output сохраняется как CI artifact;
- full tests и project notes contract зелёные.

### Риски и ограничения

Python загружает parent package `__init__.py` при анализе submodule. Domain package initializers экспортируют repositories/services, поэтому проверка четырёх model files затянула весь persistence-граф и дала 90 ошибок в девяти сторонних файлах. Этот долг нельзя маскировать ослаблением mypy и нельзя смешивать с небольшим typing-срезом.

## После завершения

### Фактически сделано

- первоначальный domain-model scope проверен и отклонён из-за heavy package exports;
- strict scope расширен на `velvet_bot/topics.py` и `velvet_bot/post_classification.py` с лёгкой package boundary;
- core access/config остаются в baseline;
- baseline test проверяет точный набор paths и запрещает `ignore_errors`/`follow_imports`;
- type-check workflow сохраняет `mypy-output.txt` artifact;
- runtime-код не изменён.

### Миграции и совместимость

PostgreSQL migrations не требуются. Topic parsing и post classification public contracts не изменены.

### Проверки

- `python -m mypy`;
- full unit/integration tests;
- project notes contract.

### PR и commit

PR создаётся из `agent/p3f-domain-models-baseline` в `main`.

### Незавершённое

Domain model files ещё не добавлены в baseline, потому что их package `__init__.py` импортируют persistence/service layers. Требуется отдельный architecture slice по lightweight domain exports либо по типизации полного package graph.

### Следующий шаг

Провести inventory тяжёлых domain `__init__.py` exports и выбрать один package для явного boundary cleanup без изменения runtime API.
