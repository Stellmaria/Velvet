# Сессия: исправление retry semantic analysis NOT NULL

- Дата: 2026-07-21
- ID: `2026-07-21-quality-retry-analysis-not-null`
- Линия/фаза: production hotfix / Qwen quality operations
- Статус: `завершено`
- Ветка: `agent/fix-quality-retry-analysis-not-null`
- Базовый commit: `69502bd87d83fd8c85862e8ed78017c301feb70f`

## Перед началом

### Цель

Исправить падение владельческой операции повторного запуска ошибочных Qwen-заданий с `asyncpg.exceptions.NotNullViolationError` для `media_ai_profiles.analysis`.

### Исходный контекст

`migrations/025_ai_media_semantics.sql` объявляет `analysis JSONB NOT NULL DEFAULT '{}'::JSONB`. Метод `QualityOperationsRepository.retry_errors()` при переводе semantic jobs из `error/skipped` в `pending` выполнял `analysis = NULL`, из-за чего вся транзакция откатывалась и кнопка повтора ошибок не работала.

### Планируемый объём

- сохранить NOT NULL invariant при сбросе semantic profile;
- не изменять применённую миграцию;
- добавить unit regression по SQL;
- добавить PostgreSQL integration regression;
- не менять callbacks, UI и worker lifecycle.

### Критерии готовности

- semantic retry переводит запись в `pending` без нарушения schema constraint;
- `analysis` сбрасывается в пустой JSON object;
- stale semantic/error/analyzed fields очищаются;
- повтор возвращает корректное число обновлённых строк;
- full tests, Docker и project notes contract зелёные.

### Риски и ограничения

Исправление должно быть совместимо с уже применённой migration 025. Изменение старого SQL-файла запрещено.

## После завершения

### Фактически сделано

- `analysis = NULL` заменено на `analysis = '{}'::JSONB`;
- сохранён существующий transaction boundary;
- unit test запрещает повторное появление `analysis = NULL`;
- PostgreSQL integration test воспроизводит error-profile и проверяет полный reset.

### Миграции и совместимость

Новая migration не требуется. Существующая схема и данные совместимы. Telegram callback и команда не изменены.

### Проверки

- targeted unit regression;
- PostgreSQL integration regression;
- full unit/integration suite;
- Docker build;
- project notes contract.

### PR и commit

PR создаётся из `agent/fix-quality-retry-analysis-not-null` в `main`.

### Незавершённое

После локального обновления требуется повторно нажать retry ошибок на живом боте и подтвердить отсутствие `NotNullViolationError`.

### Следующий шаг

После hotfix вернуться к P3A status sync, затем продолжить P3F static typing baseline.
