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

Работа начата.

### Миграции и совместимость

Планируется добавочная миграция результата и диагностических полей очереди.

### Проверки

Будут выполнены unit/integration tests, type check, Docker build, notes contract и backup restore drill.

### PR и commit

- PR: будет создан после реализации и проверки diff.
- Ветка: `agent/ai-task-queue-lifecycle`.

### Незавершённое

- queue models/repository/service;
- owner-команды;
- migration;
- tests и CI.

### Следующий шаг

Добавить модели и атомарный PostgreSQL repository lifecycle, затем owner presentation.