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

- `bootstrap.run_application()` вызывает `start_storage_librarian(bot, database)` до polling.
- cleanup вызывает `stop_storage_librarian()` до закрытия зависимостей.
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

- `velvet_bot/app/bootstrap.py` теперь владеет lifecycle Storage Librarian background scheduler: start перед polling, stop перед teardown зависимостей.
- `StorageLibrarianRepository.enqueue_pending()` учитывает существующую job до `LIMIT`: новые объекты допускаются без job, stale completed/skipped допускаются для re-analysis, queued/running/failed не блокируют продвижение к следующим объектам.
- Regression test фиксирует оба production failure modes.

### Миграции и совместимость

SQL migrations отсутствуют. Таблицы и env schema не меняются. Existing failed jobs сохраняются как evidence и не переписываются автоматически.

### Проверки

Protected CI будет запущен на PR head после публикации ветки. Production evidence уже подтверждает исходную проблему: local Ollama доступен, full-archive env активен, но job activity отсутствует после включения scheduler flags.

### PR и commit

PR и финальный head будут зафиксированы после создания pull request и terminal success required checks.

### Незавершённое

- Protected CI ещё не завершён.
- PR ещё не merged.
- Production ещё не получил application image с lifecycle hotfix.
- Production full archive flags остаются включены, но до rollout нового image scheduler фактически не стартует.

### Следующий шаг

Создать PR, дождаться terminal success required CI, синхронизировать с актуальным `main` при необходимости, выполнить merge без bypass, затем доставить exact source + verified immutable image на production и подтвердить движение `telegram_storage_analysis_jobs` и уменьшение remaining count.
