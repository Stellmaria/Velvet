# Сессия: adaptive AI queue wake-up

- Дата: 2026-08-05
- ID: 2026-08-05-adaptive-ai-queue-wakeup
- Линия/фаза: P1 PostgreSQL load reduction, issue #603
- Статус: частично
- Ветка: feat/603-adaptive-ai-queue-wakeup
- Базовый commit: 503bf696a4b723b733f8835dcc93cb5c122a7c3e

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

- добавлены typed `WorkerIterationOutcome` и `WorkerIterationResult`;
- общий `WorkerManager` получил optional adaptive wait controller, сохранив
  публичный boolean-контракт `_execute_once()` и fixed scheduling остальных workers;
- empty-only backoff использует интервалы 3/5/10/20/30 секунд и bounded jitter;
- processed iteration и PostgreSQL notification сбрасывают backoff;
- transient и terminal failures типизированы отдельно и не увеличивают empty-backoff;
- enqueue notifier вызывается после завершения durable repository write;
- dedicated PostgreSQL listener использует `LISTEN/NOTIFY`, timeout fallback polling,
  lazy reconnect и корректное закрытие при cancellation;
- worker и system-health snapshots публикуют текущий интервал, empty runs,
  processed items, wakeups, fallback polls, reconnects, listener errors и oldest queue age;
- обновлены canonical architecture, package, repository, shared-contract и P2 inventories;
- удалён устаревший `Any` exemption для worker manager; границы остальных exemptions не расширялись;
- текущий `main` с исправлением Telegram Storage #643 синхронизирован обычным
  двухродительским merge-коммитом без rebase и force-push.

### Миграции и совместимость

SQL migrations отсутствуют. Existing worker registration, manual run/restart APIs и
публичный boolean-контракт worker manager сохранены. Adaptive controller применяется
только к `ai-vision-queue`.

### Проверки

Focused correction и post-main sync workflows в hash-locked окружении с native
PostgreSQL прошли:

- Python compileall;
- `tests.test_phase6_runtime`;
- `tests.test_ai_queue_adaptive_wakeup`;
- `tests.test_telegram_storage_backup_permission_isolation`;
- `tests.test_architecture_layout_inventory`;
- `tests.test_package_architecture_inventory`;
- `tests.test_p3e_repository_layout_inventory`;
- canonical inventory write/check gates;
- deterministic jitter bounds;
- classifier-backed `ConnectionResetError` transient outcome;
- real PostgreSQL notification across independent connections;
- exact staged-path audit и branch race guard.

Временные bootstrap/correction/sync workflows удалены и отсутствуют в итоговом PR diff.
Обычный exact-head required CI запускается на owner-authored commit после generated
sync parent `3eb98a7f8860b62f260496d7718cb333a97624ca`.

### PR и commit

- PR: #642;
- synchronized base `main`: 503bf696a4b723b733f8835dcc93cb5c122a7c3e;
- generated sync parent: 3eb98a7f8860b62f260496d7718cb333a97624ca;
- final exact-head: определяется этим owner-authored worklog commit;
- merge commit: ожидается после terminal required CI PASS.

### Незавершённое

- дождаться terminal PASS всех required workflows на окончательном head;
- завершить independent exact-diff review и проверить отсутствие временных workflows;
- слить PR с expected-head SHA;
- оставить issue #603 открытым для rollout-only 60-секундного production observation,
  live reconnect/wakeup acceptance и измерения SQL/latency.

### Следующий шаг

Проверить required CI и выполнить squash merge только после terminal PASS без server operations.
