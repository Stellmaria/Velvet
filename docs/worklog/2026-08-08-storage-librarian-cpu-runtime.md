# Storage Librarian CPU runtime hardening

- Дата: 2026-08-08
- ID: `2026-08-08-storage-librarian-cpu-runtime`
- Линия/фаза: Storage Librarian / production reliability hotfix
- Статус: `в работе`
- Ветка: `fix/storage-librarian-cpu-runtime`
- Базовый commit: `66f0993780a1428b260336929f2050b424aebf1e`

## Перед началом

### Цель

Исправить доказанный production timeout локального Storage Librarian на CPU и исключить одновременный захват нескольких Storage analysis jobs независимыми worker-процессами, которые используют один локальный Ollama slot.

### Исходный контекст

Production evidence 2026-08-08 показал, что canonical `STORAGE_LIBRARIAN_RUN_TIMEOUT_SECONDS=180` недостаточен даже для single-shot анализа. Для Storage `#3597` Ollama получил prompt на 5590 tokens; через 164.10 s были обработаны только 5120 prompt tokens, после чего HTTP request был отменён на границе 2m59s, до начала generation. Небольшой Storage `#35` с 1176 prompt tokens и 256 completion tokens занял около 92.5 s model time и около 98 s HTTP wall-clock.

Отдельно production acceptance показал, что main bot и Arthur являются независимыми Storage Librarian workers с общей PostgreSQL queue и одним CPU-only `ollama-librarian`. Arthur имеет только process-local `asyncio.Lock`, поэтому другой process способен одновременно claim другого job и ждать тот же Ollama slot. Request timeout включает это ожидание.

Существующие гарантии сохраняются: Storage analysis только через local Ollama, cloud fallback отсутствует, historical failed/completed rows не переписываются ради acceptance, `STORAGE_LIBRARIAN_AUTO_ENQUEUE=false` для Arthur не меняется.

### Планируемый объём

- поднять canonical/default Storage Librarian run timeout с 180 до 720 seconds во всех runtime/config documentation surfaces;
- сериализовать Storage job claims между main, AFK и Arthur через одну PostgreSQL transaction advisory claim gate и запрет второго `running` Storage analysis job;
- сохранить target-specific Arthur claim и AFK cutoff, но провести их через общий serialized claim helper;
- не менять analyzer version, chunk limits, model, cloud routing, retry count или historical jobs;
- добавить focused regression tests на timeout default и shared claim serialization;
- обновить runbook, включая устаревшее утверждение, что hierarchical chunking не реализован.

### Критерии готовности

- default `run_timeout_seconds` равен 720 и Compose/example/runbook не возвращают 180;
- только один Storage analysis job может быть переведён из `queued` в `running` через supported repositories одновременно;
- base, AFK и Arthur target claims используют один и тот же PostgreSQL advisory transaction gate;
- второй claimant возвращает no job, пока существует `running` Storage analysis;
- target-specific Arthur и AFK predicates сохраняются;
- локальный Ollama-only contract, bounded chunking и retry budget не меняются;
- required GitHub CI проходит на exact PR head до squash merge в protected `main`.

### Риски и ограничения

Глобальная сериализация job claims означает, что stale `running` row временно блокирует новые claims до существующего stale-recovery path; это намеренно fail-closed и сохраняет уже действующую lease recovery semantics. Timeout 720 s является CPU production floor по наблюдаемой latency, а не обещанием производительности. Этот PR не запускает archive/backfill, не re-enqueue historical jobs и не выполняет production deploy.

## После завершения

### Фактически сделано

Будет заполнено после реализации и CI.

### Миграции и совместимость

SQL migration не планируется. Persistent schema и historical rows не меняются.

### Проверки

Будет заполнено после реализации и CI.

### PR и commit

Будет заполнено после открытия PR.

### Незавершённое

Production rollout и повторный controlled large hierarchical acceptance остаются отдельным шагом после merge.

### Следующий шаг

Реализовать timeout и shared claim serialization, прогнать required CI, затем squash-merge при зелёном exact head.
