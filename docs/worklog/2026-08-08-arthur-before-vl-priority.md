# Arthur-first local inference priority

- Дата: 2026-08-08
- ID: `arthur-before-vl-priority-20260808`
- Линия/фаза: VL / Storage Librarian resource arbitration
- Статус: `частично`
- Ветка: `fix/arthur-before-vl-priority-20260808`
- Базовый commit: `9a3770db95ef820c0f36e2c07a7e7c9315279e0d`
- Канонический VL источник: issue #630

## Перед началом

### Исходный контекст

Production evidence показал, что `velvet-librarian-text:v1` и `qwen3.5:9b` способны одновременно занять почти весь 8-vCPU VPS. Ручное разведение через `docker pause` уже признано небезопасным, а проверка только текущего CPU не решает задачу: bounded Storage Librarian full-archive делает паузу между циклами, хотя архивный backlog ещё не исчерпан.

Owner decision: при явно включённом Storage Librarian full-archive Arthur получает фазовый приоритет над автоматической Qwen/VL image queue. Qwen начинает automatic image analysis только после того, как Arthur исчерпал full-archive работу. Это не меняет отдельный приоритет explicit interactive owner requests из #630.

### Цель

Закрепить автоматический порядок тяжёлой локальной обработки `Arthur full-archive → automatic Qwen/VL image queue`, чтобы Arthur мог полностью завершить текущую архивную фазу без конкуренции за CPU, а Qwen начинал автоматический анализ изображений только после доказанного исчерпания Arthur backlog.

### Планируемый объём

- использовать существующий Storage Librarian repository как единый источник eligibility semantics;
- проверять текущие `queued/running` Arthur jobs до автоматического VL claim;
- если активных Arthur jobs нет, выполнять bounded `enqueue_pending(limit=1)` probe, чтобы остаточный eligible archive backlog не был принят за завершённый;
- не наращивать очередь probe-ом: при одном `queued/running` новый enqueue не выполняется;
- оставить VL task нетронутой, пока Arthur имеет приоритет;
- автоматически открыть VL queue после фактического исчерпания full-archive backlog;
- не использовать container pause/stop/restart как scheduler primitive;
- использовать существующий process-wide local-AI lock для batch VL inference внутри основного bot process;
- не включать production VL flags, controlled batch или model-routing изменения этим PR.

### Критерии готовности

- full-archive off не блокирует VL;
- существующий `queued/running` Arthur job блокирует VL без дополнительного enqueue;
- residual eligible Storage backlog ставит максимум один следующий Arthur job и держит VL закрытым;
- при Arthur priority `VisionBatchQueueConsumer` не вызывает `claim_next` VL queue;
- после полного исчерпания Arthur queue и eligible archive backlog VL consumer автоматически начинает штатный claim/process;
- invalid Librarian configuration блокирует automatic VL fail-closed;
- existing automatic/manual Storage eligibility, encryption и size boundaries не ослабляются;
- protected CI зелёный на exact PR head;
- перед merge PR head не отстаёт от `main`.

### Риски и ограничения

- gate относится к явно включённой full-archive фазе (`AUTO_ENQUEUE=true` + `AUTO_BACKFILL=true`), а не ко всем ручным Arthur requests;
- process-wide `asyncio.Lock` не является межконтейнерным lock; фазовый repository-backed gate является основным механизмом порядка Arthur full-archive → automatic VL;
- bounded probe использует существующий `enqueue_pending` и поэтому может поставить один следующий Arthur job раньше очередного 60-секундного scheduler tick, но не создаёт массовую очередь;
- новый Storage object, появившийся уже после открытия gate, не отменяет уже начатый единичный VL inference;
- изменение не является разрешением mass VL backfill;
- production rollout и feature-flag activation выполняются отдельно после merge, verified image provenance и single-image acceptance #630.

## После завершения

### Фактически сделано

`VisionBatchQueueConsumer` получил repository-backed Arthur priority gate:

- gate активен только при `STORAGE_LIBRARIAN_AUTO_ENQUEUE=true` и `STORAGE_LIBRARIAN_AUTO_BACKFILL=true`;
- invalid Librarian configuration блокирует VL fail-closed;
- сначала читаются existing Storage Librarian counts; любой `running` или `queued` job держит automatic VL закрытым;
- если активных jobs нет, вызывается существующий `StorageLibrarianRepository.enqueue_pending(settings=..., limit=1)`;
- если probe поставил один eligible archive object, VL остаётся закрытым; следующая проверка видит этот queued/running job и не может нарастить очередь;
- когда counts пусты и bounded probe возвращает `0`, Arthur full-archive считается исчерпанным и VL gate открывается.

Gate выполняется до `AITaskQueueService.claim_next()`. Пока Arthur имеет приоритет, worker возвращает `EMPTY`, оставляя VL task untouched. После открытия gate task claim и inference идут штатно. Batch VL inference также использует существующий process-wide local-AI lock для координации с другими локальными vision вызовами основного bot process.

Первоначальный отдельный production-модуль для priority predicate удалён после architecture preflight: SQL/Database acquire не должны появляться вне существующего persistence boundary, а добавление отдельного production-модуля без необходимости создавало package inventory drift.

### Миграции и совместимость

SQL migrations отсутствуют. Существующие Storage/VL rows, queue schema и image profile schema не меняются. Новых обязательных env vars нет: gate использует уже существующие `STORAGE_LIBRARIAN_AUTO_ENQUEUE`, `STORAGE_LIBRARIAN_AUTO_BACKFILL` и `StorageLibrarianSettings`.

`LOCAL_UNCENSORED`, `CLOUD_PRO`, vision-gateway и model/runtime lifecycle этим изменением не затрагиваются. Existing full-archive eligibility, batch size и scan interval сохраняются; gate повторно использует `enqueue_pending` вместо отдельной SQL-копии.

### Проверки

Добавлен `tests/test_local_inference_priority.py`, который проверяет:

1. выключенный full-archive не блокирует VL и не обращается к repository;
2. существующий Arthur job блокирует VL без дополнительного enqueue;
3. residual archive backlog через bounded probe ставит ровно один job и блокирует VL;
4. gate открывается после пустой Arthur queue и `enqueue_pending(..., limit=1) == 0`;
5. invalid Librarian configuration блокирует VL fail-closed;
6. VL consumer при Arthur priority не вызывает `claim_next` и не запускает processor;
7. после снятия priority consumer claim-ит и завершает ровно одну VL task.

Первый PR head `ff29817ba083d3c82013b8934fb6d05944373e57` получил успешный `type check`; project-notes corrections были завершены на следующих heads. Exact head `175ed779cc54328850d577d7d642932a1543f150` прошёл worklog/type-check, но fast architecture preflight отклонил отдельный `velvet_bot/domains/local_inference_priority.py` за SQL/Database acquire вне persistence и package inventory drift. Реализация после этого перенесена в существующий worker с повторным использованием `StorageLibrarianRepository`, а отдельный production-модуль удалён.

После устранения новых architecture violations checker на `6e867f20258c37f161b332276550b77feb333aee` сообщал только stale generated inventory. Штатный одноразовый package-architecture preview был восстановлен из исторического governance flow, запущен с source head `2eb13884d1620491cc4435fb1ff27a1185aa5500` и успешно создал generated commit `8ea22c3754fe983eaf8299f0333f67ca574a0135`. В generated commit temporary workflow удалён из tree; generated inventory/exemptions созданы штатным scanner с label `p1-package-architecture-baseline`.

Generated commit от `github-actions[bot]` не запускает обычную цепочку GitHub Actions повторно, поэтому текущий docs-only commit служит явным CI kick без изменения production source или generated architecture baseline.

### PR и commit

- PR: `#741` — `Prioritize Arthur full-archive before automatic VL`.
- Ветка: `fix/arthur-before-vl-priority-20260808`.
- Базовый `main`: `9a3770db95ef820c0f36e2c07a7e7c9315279e0d`.
- Generated architecture commit: `8ea22c3754fe983eaf8299f0333f67ca574a0135`.
- Финальный exact head и squash merge commit фиксируются после terminal success protected CI.

### Незавершённое

- protected CI ещё должен завершиться зелёным на exact final head;
- PR ещё не merged;
- production application image с этим scheduler contract ещё не опубликован и не развёрнут;
- канонический post-#738 single-image `512 / 1` LOCAL_MAIN acceptance ещё не завершён;
- automatic Qwen image queue не должна включаться до этого acceptance.

### Следующий шаг

Дождаться terminal success всех required checks на exact PR head, проверить актуальный `main` и `behind_by=0`, выполнить authorized squash merge #741 с expected head SHA. После merge зафиксировать решение в #630. Production rollout выполнять отдельно через verified application image; Arthur full-archive при этом может продолжать свою текущую фазу, а automatic Qwen activation остаётся после single-image acceptance.
