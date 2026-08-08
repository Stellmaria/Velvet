# Storage Librarian scheduler lifecycle hotfix

- Дата: 2026-08-08
- ID: storage-librarian-scheduler-lifecycle-20260808
- Линия/фаза: Arthur / Storage Librarian production backfill
- Статус: `частично`
- Ветка: `fix/storage-librarian-scheduler-lifecycle`
- Базовый commit: `42bd97eedd0807befb92cfcd56cd231e9cc51567`

## Перед началом

### Цель

Довести уже включённый bounded full-archive Storage Librarian до фактической фоновой обработки production-архива через локальный Ollama.

### Исходный контекст

Production rollout уже включил:

- `STORAGE_LIBRARIAN_ENABLED=true`;
- `STORAGE_LIBRARIAN_AUTO_ENQUEUE=true`;
- `STORAGE_LIBRARIAN_AUTO_BACKFILL=true`;
- `STORAGE_LIBRARIAN_AUTO_MIN_OBJECT_ID=0`;
- batch `1` и scan interval `60` секунд;
- local-only `http://ollama-librarian:11434`;
- Arthur container оставлен с `AUTO_ENQUEUE=false`, чтобы не запускать второй scheduler.

Production diagnostics подтвердили, что основной bot healthy и видит локальный Ollama (`/api/tags` -> HTTP 200), однако после включения full archive не было ни одного изменения `telegram_storage_analysis_jobs` за ожидаемые фоновые циклы. В базе оставалось 2198 объектов без current-version analysis.

Поиск по текущему исходному коду показал, что `start_storage_librarian()` и `stop_storage_librarian()` были определены, но application lifecycle их не вызывал. Env flags поэтому отображались корректно, но background task фактически не создавался.

Дополнительно production jobs показали terminal `failed` записи от fail-closed text-context guard. Старый `enqueue_pending()` выбирал объект до проверки существующего terminal job и ограничивал выборку `LIMIT 1`. Такой объект мог постоянно выигрывать сортировку, конфликтовать с уже существующей `failed` job и блокировать продвижение full archive к следующим объектам.

### Планируемый объём

- Явно запускать Storage Librarian scheduler после создания bot/database и до Telegram polling.
- Явно останавливать scheduler до закрытия worker manager, bot session и PostgreSQL pool.
- Не менять full-archive batch/concurrency: по умолчанию остаётся один объект за цикл.
- Не ослаблять local-only Ollama contract.
- Не переоткрывать terminal failed jobs автоматически.
- Изменить `enqueue_pending()` так, чтобы existing queued/running/failed jobs не блокировали выбор следующего eligible объекта.
- Сохранить re-analysis stale completed/skipped rows при смене analyzer version.
- Добавить regression contract на lifecycle wiring и failed-job progress.

### Критерии готовности

- Application lifecycle запускает Storage Librarian background scheduler до polling.
- Cleanup останавливает scheduler до закрытия зависимостей.
- full-archive selection не выбирает existing queued/running/failed jobs как кандидатов для нового enqueue.
- stale completed/skipped analysis по-прежнему может быть requeued новой analyzer version.
- Existing fail-closed text-context policy, encryption, size and allowed-kind boundaries не меняются.
- Protected CI зелёный на exact PR head.
- Merge выполняется без обхода branch protection.

### Риски и ограничения

- Terminal failed объекты не считаются успешно проанализированными и не будут автоматически retry-loop'иться full archive scheduler'ом.
- Oversized extracted text по-прежнему fail closed; chunking и silent truncation не добавляются этим hotfix.
- Full archive на CPU-only Ollama может обрабатываться долго, поскольку batch остаётся `1`.
- Production checkout/runtime provenance должен быть повторно выровнен отдельным verified rollout после merge.

## После завершения

### Фактически сделано

- `velvet_bot/app/bootstrap.py` теперь владеет lifecycle Storage Librarian background scheduler через bounded start/stop helpers: start перед polling, stop перед teardown зависимостей.
- Новый lifecycle wiring не увеличивает существующий architectural monolithic-function fingerprint `velvet_bot/app/bootstrap.py`; max function остаётся 181 строка.
- `StorageLibrarianRepository.enqueue_pending()` учитывает существующую job до `LIMIT`: новые объекты допускаются без job, stale completed/skipped допускаются для re-analysis, queued/running/failed не блокируют продвижение к следующим объектам.
- Regression test фиксирует оба production failure modes.
- Generated package architecture baseline обновлён до `production_loc=144224`; violation count остаётся 523, новый architecture debt не добавлен.
- Временный workflow, использованный только для детерминированной генерации inventory, удалён из feature branch до финального CI.

### Миграции и совместимость

SQL migrations отсутствуют. Таблицы и env schema не меняются. Existing failed jobs сохраняются как evidence и не переписываются автоматически.

### Проверки

Initial PR head подтвердил `type check`, project notes, branch protection, Docker build и security supply chain. Первый tests run упал только на stale architecture/P2 generated contracts после первоначального более длинного lifecycle wiring.

После рефакторинга lifecycle wiring возвращён к прежнему bootstrap fingerprint и без нового exception boundary. Package architecture inventory регенерирован штатным `scripts/inventory_package_architecture.py`: 656 production modules, 144224 LOC, 523 violations, bootstrap max function 181 и прежний exemption fingerprint.

После merge актуального `main` все четыре test shards прошли; integrated regeneration подтвердил те же `production_loc=144224` и `violation_count=523`, а временный refresh workflow удалил только себя. Финальный обычный PR CI запускается на чистом integrated head.

### PR и commit

- PR: `#722` — `Fix Storage Librarian full-archive scheduler lifecycle`.
- Ветка: `fix/storage-librarian-scheduler-lifecycle`.
- Initial PR head: `7534a6074a80a5ad6586c0e16e7cecb01f88c880`.
- Generated-baseline head: `ba06d19c72fc298ce1d3b9eb45ee5a6c074ef53f`.
- Integrated main parent: `f0223d62a5b9039fa92c7d50929418d92fdf2f43`.
- Финальный PR head и squash merge SHA будут зафиксированы после terminal success required checks.

### Незавершённое

- Финальный protected CI ещё не завершён.
- PR ещё не merged.
- Production ещё не получил application image с lifecycle hotfix.
- Production full archive flags остаются включены, но до rollout нового image scheduler фактически не стартует.

### Следующий шаг

Дождаться terminal success required CI на exact PR head, при необходимости синхронизировать ветку с актуальным `main`, выполнить squash merge без bypass, затем доставить exact source + verified immutable image на production и подтвердить движение `telegram_storage_analysis_jobs` и уменьшение remaining count.
