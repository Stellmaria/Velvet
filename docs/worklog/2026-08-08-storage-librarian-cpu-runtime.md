# Storage Librarian CPU runtime hardening

- Дата: 2026-08-08
- ID: `2026-08-08-storage-librarian-cpu-runtime`
- Линия/фаза: Storage Librarian / production reliability hotfix
- Статус: `частично`
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
- legacy timeout override ниже 720 не может опустить effective runtime ниже CPU floor;
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

`StorageLibrarianSettings` получил effective CPU floor `720` seconds: default равен 720, legacy env override ниже floor автоматически поднимается до 720, а больший override сохраняется до существующего верхнего лимита 1800. Canonical `.env.server.example`, Librarian env example и Compose defaults обновлены на 720.

`StorageLibrarianRepository` получил общий `_claim_next()` с PostgreSQL transaction advisory lock. В одной claim transaction проверяется отсутствие любого `running` Storage job и только затем один queued row переводится в `running`. Advisory lock не удерживается во время inference и не занимает connection на время Ollama request. Base `claim_next()`, Arthur exact-target repository и AFK cutoff repository теперь проходят через один helper, сохраняя свои predicates.

Добавлен `tests/test_storage_librarian_claim_serialization.py`, который фиксирует общий advisory gate, one-running predicate, exact Arthur target и AFK cutoff. Existing settings/contracts обновлены на CPU-safe timeout floor. Runbook исправлен: hierarchical chunking теперь описан как действующий bounded path с canonical hard cap `132096` chars для `8192/384`, `12` chunks и `13` inference calls, а не как отсутствующая возможность.

### Миграции и совместимость

SQL migration отсутствует. Persistent schema, analyzer version, existing jobs/analyses, chunk limits, model selection и retry budget не меняются. `STORAGE_LIBRARIAN_AUTO_ENQUEUE=false` для Arthur сохраняется. Historical queue rows не reset/re-enqueue этим PR.

### Проверки

Focused regression tests и full required GitHub CI должны пройти на PR exact head. Production live verification не выполняется этим PR.

### PR и commit

PR будет открыт из `fix/storage-librarian-cpu-runtime` в protected `main`; exact head и terminal CI будут зафиксированы перед merge.

### Незавершённое

Production rollout и повторный controlled large hierarchical acceptance остаются отдельным шагом после merge. Отдельные production defects `enqueue_object()` reset semantics и Arthur report publication `chat not found` не входят в этот hotfix.

### Следующий шаг

Открыть PR, получить terminal success required CI на exact head, перевести worklog в `завершено`, затем squash-merge без bypass/force.