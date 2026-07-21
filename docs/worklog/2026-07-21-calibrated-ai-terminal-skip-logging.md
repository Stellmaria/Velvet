# Сессия: calibrated AI terminal skip logging

- Дата: 2026-07-21
- ID: `2026-07-21-calibrated-ai-terminal-skip-logging`
- Линия/фаза: production hotfix / AI quality observability
- Статус: `завершено`
- Ветка: `agent/downgrade-calibrated-terminal-skips`
- Базовый commit: `57114e01ccb6d05e220ac256f4b9d2ce7ecea938`

## Перед началом

### Цель

Убрать ложные Error Center incidents для permanent AI skips, когда Telegram не позволяет скачать слишком крупное изображение и не предоставляет доступную миниатюру.

### Исходный контекст

`CalibratedAIQualityService` уже определял такие `VisionAnalysisError` как permanent и переводил задание в `skipped`, однако до определения permanent всегда писал `logger.warning`. Error Center воспринимал ожидаемый terminal skip как новый warning incident.

### Планируемый объём

- вычислять permanent до записи лога;
- permanent skip писать как `INFO`;
- настоящие временные и неожиданные ошибки оставлять `WARNING`;
- сохранить существующий status/error_message и отсутствие автоматического retry;
- добавить поведенческие regression tests.

### Критерии готовности

- oversized/no-preview case не создаёт warning log;
- задание отмечается permanent и не возвращается в автоматическую очередь;
- unrelated runtime failure остаётся warning и retryable;
- full tests, Docker и project notes contract зелёные.

### Риски и ограничения

Исправление не должно скрывать provider, database, filesystem или Telegram failures. Понижение уровня применяется только к уже классифицированному `VisionAnalysisError` с известными terminal markers.

## После завершения

### Фактически сделано

- добавлена явная классификация permanent analysis error;
- permanent skips логируются на INFO;
- настоящие ошибки продолжают логироваться на WARNING;
- добавлены tests для обоих путей и аргумента `permanent` в repository compensation.

### Миграции и совместимость

PostgreSQL migrations не требуются. Статусы AI quality jobs, Telegram callbacks и UI не изменены.

### Проверки

- terminal oversized skip logging test;
- unrelated retryable failure logging test;
- full test suite;
- Docker build;
- project notes contract.

### PR и commit

PR создаётся из `agent/downgrade-calibrated-terminal-skips` в `main`.

### Незавершённое

Уже созданные warning incidents №49–51 останутся в истории Error Center как просмотренные; новые аналогичные записи после обновления не должны появляться.

### Следующий шаг

После hotfix вернуться к P3A status sync и затем начать P3F static typing baseline.
