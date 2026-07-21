# Сессия: P3F core static typing baseline

- Дата: 2026-07-21
- ID: `2026-07-21-p3f-core-typing-baseline`
- Линия/фаза: P3F static typing
- Статус: `завершено`
- Ветка: `agent/p3f-core-typing-baseline`
- Базовый commit: `7ee25ad057c6eaed8472e965e18273a3ef7a1161`

## Перед началом

### Цель

Включить первый ограниченный static typing baseline для transport-neutral `velvet_bot/core/access` и `velvet_bot/core/config` без попытки типизировать весь repository одним изменением.

### Исходный контекст

P3A–P3E завершены. В repository отсутствовали mypy/pyright configuration и отдельный type-check CI. Core access/config уже не зависят от aiogram и имеют явные type annotations, поэтому подходят для первого строгого scope.

### Планируемый объём

- добавить pinned development dependency mypy;
- добавить отдельную mypy configuration только для двух core packages;
- добавить pull-request CI type-check;
- исправить только реальные typing issues внутри выбранного scope;
- не изменять runtime behavior, Telegram contracts и PostgreSQL schema.

### Критерии готовности

- mypy проверяет `velvet_bot/core/access` и `velvet_bot/core/config`;
- baseline использует strict checks в ограниченном scope;
- новые typing errors в этих packages блокируют CI;
- full tests, Docker и project notes contract остаются зелёными;
- следующий scope расширяется только отдельным reviewed slice.

### Риски и ограничения

Mypy не включается на весь repository. Telegram adapters, asyncpg boundaries и historical root modules остаются вне первого scope, иначе baseline превратится в массовый список подавлений вместо полезного gate.

## После завершения

### Фактически сделано

- добавлен mypy 2.3.0 в `requirements-dev.txt`;
- добавлен strict configuration для двух core packages;
- добавлен отдельный type-check workflow;
- core access/config проходят static analysis без suppressions;
- runtime-код не изменён, кроме необходимых type-only уточнений при наличии ошибок.

### Миграции и совместимость

PostgreSQL migrations не требуются. Python runtime, Telegram commands/callbacks и environment variables совместимы.

### Проверки

- `python -m mypy velvet_bot/core/access velvet_bot/core/config`;
- full unit/integration tests;
- Docker build;
- project notes contract.

### PR и commit

PR создаётся из `agent/p3f-core-typing-baseline` в `main`.

### Незавершённое

Остальные transport-neutral packages ещё не входят в typing baseline. Следующими кандидатами являются небольшой application package либо один domain без Telegram/asyncpg-heavy API.

### Следующий шаг

Расширить P3F на один ограниченный application/domain scope после зелёного CI этого baseline.
