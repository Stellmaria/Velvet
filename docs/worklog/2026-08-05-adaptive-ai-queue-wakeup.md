# Сессия: adaptive AI queue wake-up

- Дата: 2026-08-05
- ID: 2026-08-05-adaptive-ai-queue-wakeup
- Линия/фаза: P1 PostgreSQL load reduction, issue #603
- Статус: частично
- Ветка: feat/603-adaptive-ai-queue-wakeup
- Базовый commit: 1a56d7b9d2fea7a967ba12c5a119b53d0dfb8e5c

## Перед началом

### Цель

Убрать постоянный трёхсекундный SQL polling пустой очереди VL-задач, сохранив
быстрый старт после enqueue, fail-closed claim semantics, отсутствие overlap и
работу при потере PostgreSQL notification connection.

### Исходный контекст

`ai-vision-queue` использовал общий `PeriodicWorkerSpec(interval_seconds=3)`.
`VisionBatchQueueConsumer.process_once()` возвращал неразличимые `0/1`, а
`WorkerManager` игнорировал результат и всегда выполнял следующий claim через
три секунды. В репозитории отсутствовали LISTEN/NOTIFY и adaptive wait contract.

### Планируемый объём

- ввести typed outcome для processed/empty/skipped/transient/terminal iteration;
- добавить optional wait controller в общий worker manager без изменения других workers;
- реализовать bounded adaptive backoff 3/5/10/20/30 секунд с jitter;
- добавить PostgreSQL notifier после committed enqueue и dedicated LISTEN connection;
- сохранить timeout polling как fallback и переподключаться после termination;
- публиковать backoff, wake-up, reconnect и queue-age counters в health snapshot;
- добавить unit и PostgreSQL integration tests.

### Критерии готовности

- пустые claim последовательно увеличивают интервал до 30 секунд;
- успешная обработка и notification сбрасывают backoff;
- enqueue notification выполняется только после возврата durable repository write;
- потеря listener не останавливает worker и приводит к fallback polling/reconnect;
- transient/terminal task failure не классифицируется как empty;
- один worker не выполняет overlapping iterations;
- остальные periodic workers сохраняют прежний fixed interval contract;
- exact-head required CI проходит перед merge.

### Риски и ограничения

- PostgreSQL NOTIFY является подсказкой, а не durable queue;
- уведомление может быть потеряно между commit и установкой listener, поэтому timeout polling обязателен;
- live SQL/latency measurement требует server acceptance и не выполняется в этом PR;
- SQL migration, deploy, restart и production configuration отсутствуют.

## После завершения

### Фактически сделано

- ожидается после implementation и exact-head CI.

### Миграции и совместимость

SQL migrations отсутствуют. Existing worker registration и manual run/restart APIs
сохраняются; adaptive controller используется только `ai-vision-queue`.

### Проверки

- ожидаются после публикации PR.

### PR и commit

- PR: ожидается;
- implementation head: ожидается;
- final merge commit: ожидается после required CI.

### Незавершённое

- опубликовать implementation branch;
- пройти focused и full required CI;
- выполнить independent exact-diff review;
- слить PR при terminal PASS;
- live measurement оставить отдельным rollout-only evidence.

### Следующий шаг

Опубликовать атомарный implementation tree, запустить exact-head CI и устранить
только подтверждённые test/review findings.
