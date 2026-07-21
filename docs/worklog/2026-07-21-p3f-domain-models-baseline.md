# Сессия: P3F domain models static typing baseline

- Дата: 2026-07-21
- ID: `2026-07-21-p3f-domain-models-baseline`
- Линия/фаза: P3F static typing
- Статус: `завершено`
- Ветка: `agent/p3f-domain-models-baseline`
- Базовый commit: `a16b38892b420111c7d7696fb26b0b6eca02b873`

## Перед началом

### Цель

Расширить strict mypy baseline с core на небольшой transport-neutral слой доменных dataclasses: characters, archive, references и stories models.

### Исходный контекст

Первый P3F-срез уже проверяет `velvet_bot/core/access` и `velvet_bot/core/config`. Следующий безопасный scope состоит из чистых model modules без aiogram, SQL, asyncpg и внешних network clients.

### Планируемый объём

- добавить четыре domain model modules в существующий mypy scope;
- обновить regression-test baseline;
- исправить только реальные typing issues в выбранных model files;
- не включать repositories, services, workers и Telegram adapters;
- не менять runtime behavior.

### Критерии готовности

- mypy strict проверяет core и выбранные domain models;
- baseline перечислен явно и защищён тестом;
- `ignore_errors` и широкие suppressions отсутствуют;
- full tests и project notes contract зелёные;
- следующий scope добавляется отдельным reviewed slice.

### Риски и ограничения

Импортируемые domain types должны оставаться transport-neutral. Если scope начнёт тянуть persistence или Telegram modules, он сокращается, а не маскируется `follow_imports=skip`.

## После завершения

### Фактически сделано

- strict scope расширен на characters/archive/references/stories models;
- baseline test проверяет точный набор paths;
- model files проходят mypy без suppressions;
- runtime-код не изменён, кроме возможных type-only уточнений.

### Миграции и совместимость

PostgreSQL migrations не требуются. Dataclass fields и public imports сохраняются.

### Проверки

- `python -m mypy`;
- full unit/integration tests;
- project notes contract.

### PR и commit

PR создаётся из `agent/p3f-domain-models-baseline` в `main`.

### Незавершённое

Repository/service/worker scopes ещё не типизированы. Dynamic Telegram storage settings и visual fingerprint остаются отдельными кандидатами.

### Следующий шаг

Добавить один bounded service/application scope либо чистые discussion/domain models после отдельной проверки imports.
