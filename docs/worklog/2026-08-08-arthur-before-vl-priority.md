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

Owner decision: при явно включённом Storage Librarian full-archive Arthur получает фазовый приоритет над автоматической Qwen/VL image queue. Qwen начинает автоматический image analysis только после того, как Arthur исчерпал full-archive работу. Это не меняет отдельный приоритет explicit interactive owner requests из #630.

### Цель

Закрепить автоматический порядок тяжёлой локальной обработки `Arthur full-archive → automatic Qwen/VL image queue`, чтобы Arthur мог полностью завершить текущую архивную фазу без конкуренции за CPU, а Qwen начинал автоматический анализ изображений только после доказанного исчерпания Arthur backlog.

### Планируемый объём

- добавить DB-backed predicate незавершённой Arthur full-archive фазы;
- учитывать не только `queued/running`, но и eligible Storage objects без analysis текущей `analyzer_version`;
- проверять Arthur priority до claim автоматической VL task;
- оставить VL task нетронутой, пока Arthur имеет приоритет;
- автоматически открыть VL queue после фактического исчерпания full-archive backlog;
- не использовать container pause/stop/restart как scheduler primitive;
- использовать существующий process-wide local-AI lock для batch VL inference внутри основного bot process;
- не включать production VL flags, controlled batch или model-routing изменения этим PR.

### Критерии готовности

- full-archive off не блокирует VL;
- residual eligible Storage backlog держит VL закрытым даже между Arthur scheduler cycles;
- при Arthur priority `VisionBatchQueueConsumer` не вызывает `claim_next`;
- после полного исчерпания Arthur backlog VL consumer автоматически начинает штатный claim/process;
- invalid Librarian configuration блокирует автоматический VL fail-closed;
- existing automatic/manual Storage eligibility, encryption и size boundaries не ослабляются;
- protected CI зелёный на exact PR head;
- перед merge PR head не отстаёт от `main`.

### Риски и ограничения

- gate относится к явно включённой full-archive фазе (`AUTO_ENQUEUE=true` + `AUTO_BACKFILL=true`), а не ко всем ручным Arthur requests;
- process-wide `asyncio.Lock` не является межконтейнерным lock; фазовый DB predicate является основным механизмом порядка Arthur full-archive → automatic VL;
- новый Storage object, появившийся уже после открытия gate, относится к будущей arbitration hardening и не должен отменять уже начатый единичный VL inference;
- изменение не является разрешением mass VL backfill;
- production rollout и feature-flag activation выполняются отдельно после merge, verified image provenance и single-image acceptance #630.

## После завершения

### Фактически сделано

Добавлен `storage_librarian_full_archive_has_priority()`:

- gate активен только при `STORAGE_LIBRARIAN_AUTO_ENQUEUE=true` и `STORAGE_LIBRARIAN_AUTO_BACKFILL=true`;
- invalid Librarian configuration блокирует VL fail-closed;
- PostgreSQL predicate считает приоритетной работой текущие `running` Librarian jobs, claimable `queued` jobs и ещё не поставленные в очередь eligible Storage objects без analysis текущей `analyzer_version`;
- terminal/exhausted work не держит VL закрытым бесконечно.

`VisionBatchQueueConsumer` проверяет gate до `AITaskQueueService.claim_next()`. Пока Arthur имеет приоритет, worker возвращает `EMPTY`, оставляя VL task untouched. После открытия gate task claim и inference идут штатно. Batch VL inference также использует существующий process-wide local-AI lock для координации с другими локальными vision вызовами основного bot process.

### Миграции и совместимость

SQL migrations отсутствуют. Существующие Storage/VL rows, queue schema и image profile schema не меняются. Новых обязательных env vars нет: gate использует уже существующие `STORAGE_LIBRARIAN_AUTO_ENQUEUE`, `STORAGE_LIBRARIAN_AUTO_BACKFILL` и `StorageLibrarianSettings`.

`LOCAL_UNCENSORED`, `CLOUD_PRO`, vision-gateway и model/runtime lifecycle этим изменением не затрагиваются. Existing full-archive batch size и scan interval сохраняются.

### Проверки

Добавлен `tests/test_local_inference_priority.py`, который проверяет:

1. выключенный full-archive не блокирует VL;
2. остаточный Storage backlog держит gate закрытым даже без текущего running job;
3. gate открывается после исчерпания backlog;
4. invalid Librarian configuration блокирует VL fail-closed;
5. VL consumer при Arthur priority не вызывает `claim_next` и не запускает processor;
6. после снятия priority consumer claim-ит и завершает ровно одну VL task.

Первый PR head `ff29817ba083d3c82013b8934fb6d05944373e57` уже получил успешный `type check`; `project notes contract` выявил только несоответствие обязательной структуре этого worklog. Следующий head `b43359454fac6cef3783d9e700897687dc55facb` подтвердил, что оставалась только обязательная секция `### Цель`, добавленная текущим commit. Полный protected CI должен быть повторно подтверждён на новом exact head.

### PR и commit

- PR: `#741` — `Prioritize Arthur full-archive before automatic VL`.
- Ветка: `fix/arthur-before-vl-priority-20260808`.
- Базовый `main`: `9a3770db95ef820c0f36e2c07a7e7c9315279e0d`.
- Первый CI head: `ff29817ba083d3c82013b8934fb6d05944373e57`.
- Финальный exact head и squash merge commit фиксируются после terminal success protected CI.

### Незавершённое

- protected CI ещё должен завершиться зелёным на exact head после worklog correction;
- PR ещё не merged;
- production application image с этим scheduler contract ещё не опубликован и не развёрнут;
- канонический post-#738 single-image `512 / 1` LOCAL_MAIN acceptance ещё не завершён;
- automatic Qwen image queue не должна включаться до этого acceptance.

### Следующий шаг

Дождаться terminal success всех required checks на exact PR head, проверить актуальный `main` и `behind_by=0`, выполнить authorized squash merge #741 с expected head SHA. После merge зафиксировать решение в #630. Production rollout выполнять отдельно через verified application image; Arthur full-archive при этом может продолжать свою текущую фазу, а automatic Qwen activation остаётся после single-image acceptance.
