# 2026-07-28 — lifecycle очереди AI-задач

- Дата: 2026-07-28
- ID: ai-task-queue-lifecycle
- Линия/фаза: Линия B — Velvet AI / task queue
- Статус: `частично`
- Ветка: `agent/ai-task-queue-lifecycle`
- Базовый commit: `e3881899cff7234752d479938b0221249838a61b`

## Перед началом

### Цель

Превратить существующую таблицу `ai_tasks` в рабочую PostgreSQL-очередь с атомарной постановкой, claim через `FOR UPDATE SKIP LOCKED`, retry/backoff, восстановлением зависших задач и owner-наблюдаемостью из Telegram.

### Исходный контекст

После PR #349 таблица `ai_tasks` существует, но repository и lifecycle отсутствуют. После PR #352 смысловой VL-анализ уже имеет budget executor и cache, однако пакетная постановка, конкурентные workers и безопасное восстановление задач ещё не реализованы. Без queue contract будущий массовый импорт снова пришлось бы строить вокруг прямого polling отдельных таблиц.

### Планируемый объём

- добавить transport-neutral модели AI-задач и статусов;
- реализовать enqueue и enqueue-many с dedupe key;
- реализовать атомарный claim по priority/not_before через `FOR UPDATE SKIP LOCKED`;
- учитывать глобальный pause AI-контура при claim;
- реализовать complete, cancel, heartbeat и fail с exponential backoff;
- переводить исчерпавшие attempts задачи в terminal error;
- восстанавливать stale running tasks без создания дублей;
- добавить counts/recent inspection и owner-команды `/ai_queue`, `/ai_queue_retry`, `/ai_queue_cancel`;
- зарегистрировать команды в owner access/help/UI contract;
- добавить PostgreSQL concurrency tests и unit-тесты форматирования.

### Критерии готовности

- два workers не могут одновременно claim одну задачу;
- одинаковый активный dedupe key не создаёт второй task;
- paused AI runtime не выдаёт новые задачи;
- fail возвращает задачу в queued с future not_before до исчерпания attempts;
- последний fail переводит задачу в error;
- stale running task возвращается в queued либо error согласно attempt_count;
- owner видит counts и последние задачи без SQL в handler;
- owner может requeue terminal task и cancel active task;
- tests, type check, Docker build, notes contract и backup restore drill проходят.

### Риски и ограничения

- этот PR создаёт общий queue lifecycle, но не переводит semantic worker на `ai_tasks`;
- пакетная постановка изображений и предварительное подтверждение стоимости остаются следующим срезом;
- webhook/event-driven запуск не добавляется, workers продолжают polling с безопасным интервалом;
- applied migration `z004` не редактируется, расширения оформляются новой `z007`.

## После завершения

### Фактически сделано

- добавлены transport-neutral модели `AITask`, `AITaskRequest`, `AITaskStatus`, enqueue/failure results и queue snapshot;
- реализованы одиночная и пакетная постановка задач с активным partial-unique `dedupe_key`;
- атомарный claim использует `FOR UPDATE SKIP LOCKED` и не выдаёт одну задачу двум workers;
- claim учитывает глобальный pause в `ai_runtime_state`;
- добавлены heartbeat, complete с JSONB-result, cancel и ручной requeue terminal-задач;
- fail использует exponential backoff, сохраняет тип и текст ошибки и после исчерпания attempts переводит задачу в `error`;
- stale running locks автоматически возвращаются в `queued` либо завершаются `error` согласно attempt_count/max_attempts;
- зарегистрирован бесплатный background worker `ai-task-stale-recovery`, не вызывающий модели;
- один `AITaskQueueService` разделяется между background workers и Telegram composition root;
- добавлены owner-команды `/ai_queue`, `/ai_queue_retry`, `/ai_queue_cancel`;
- owner-интерфейс показывает counts, status, priority, attempts, estimated cost, worker lock, retry delay и ошибку;
- команды зарегистрированы в owner-only access, полном help и UI/direct command contracts;
- исправлено явное декодирование JSONB payload/result для конфигураций asyncpg, возвращающих строки;
- добавлены PostgreSQL integration tests active dedupe, concurrent claim, pause, retry, completion, stale recovery и cancel/requeue;
- добавлены unit-тесты owner formatting/access и обновлён точный worker registry.

### Миграции и совместимость

Добавлена новая неизменяемая миграция `migrations/z007_ai_task_queue_lifecycle.sql`. Она расширяет существующую `ai_tasks` полями `result`, `estimated_cost_rub`, `last_error_type` и `last_retry_delay_seconds`, а также добавляет индексы running-lock и terminal history. Старая `z004` не изменена. Существующие строки получают безопасные значения по умолчанию. Backup/restore drill подтвердил применение и восстановление схемы. Отдельный Redis или внешний брокер не требуется.

### Проверки

На head `2cd60d06f5035d4a9742bf2412f17fb15a90b22f` успешно прошли:

- tests workflow `#2087`: 1489 тестов;
- type check `#740`;
- Docker build `#1466`;
- project notes contract `#1324`;
- backup restore drill `#469`.

Live production-smoke owner-команд и реальных queue consumers намеренно не выполнялся в CI.

### PR и commit

- PR: `#353` — «Добавить lifecycle PostgreSQL-очереди AI-задач».
- Ветка: `agent/ai-task-queue-lifecycle`.
- Проверенный head: `2cd60d06f5035d4a9742bf2412f17fb15a90b22f`.

### Незавершённое

- перевод semantic VL worker с прямого polling `media_ai_profiles` на `ai_tasks`;
- пакетная постановка изображений;
- предварительная оценка максимальной стоимости партии и подтверждение владельца;
- heartbeat во время длительного реального provider call;
- per-task progress и batch grouping;
- live Telegram-smoke `/ai_queue`, retry и cancel после обновления production.

### Следующий шаг

Добавить пакет semantic VL-задач с предварительным расчётом максимальной стоимости, owner-подтверждением и queue consumer, который вызывает существующий Flash → Pro → sensitive router.