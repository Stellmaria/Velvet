# Arthur-first local inference priority

- Дата: 2026-08-08
- ID: `arthur-before-vl-priority-20260808`
- Линия/фаза: VL / Storage Librarian resource arbitration
- Статус: `в работе`
- Ветка: `fix/arthur-before-vl-priority-20260808`
- Базовый commit: `9a3770db95ef820c0f36e2c07a7e7c9315279e0d`
- Канонический VL источник: issue #630

## Перед началом

### Причина

Production evidence показал, что `velvet-librarian-text:v1` и `qwen3.5:9b` способны одновременно занять почти весь 8-vCPU VPS. Ручное разведение через `docker pause` уже признано небезопасным, а проверка только текущего CPU не решает задачу: bounded Storage Librarian full-archive делает паузу между циклами, хотя архивный backlog ещё не исчерпан.

Owner decision: при явно включённом Storage Librarian full-archive Arthur получает фазовый приоритет над автоматической Qwen/VL image queue. Qwen начинает автоматический image analysis только после того, как Arthur исчерпал full-archive работу.

### Цель

- не выключать Arthur ради обычной эксплуатации;
- не запускать Qwen VL между двумя Arthur full-archive циклами;
- не claim-ить image task, пока Arthur имеет приоритет;
- автоматически открыть VL queue после фактического завершения full archive;
- не использовать container pause/stop/restart как scheduler primitive;
- сохранить один local VL inference через существующий process-wide local-AI lock.

## Реализация

Добавлен `storage_librarian_full_archive_has_priority()`:

- gate активен только при `STORAGE_LIBRARIAN_AUTO_ENQUEUE=true` и `STORAGE_LIBRARIAN_AUTO_BACKFILL=true`;
- invalid Librarian configuration блокирует VL fail-closed;
- PostgreSQL predicate считает приоритетной работой:
  - текущие `running` Librarian jobs;
  - claimable `queued` Librarian jobs;
  - ещё не поставленные в очередь eligible Storage objects без analysis текущей `analyzer_version`;
- terminal/exhausted work не держит VL закрытым бесконечно.

`VisionBatchQueueConsumer` проверяет gate до `AITaskQueueService.claim_next()`. Пока Arthur имеет приоритет, worker возвращает `EMPTY`, оставляя VL task untouched. После открытия gate task claim и inference идут штатно. Batch inference также использует существующий process-wide local-AI lock, чтобы не конкурировать с другими локальными vision вызовами того же bot process.

## Границы

- Изменение не включает `AI_VISION_ENABLED` и не запускает controlled batch само по себе.
- Изменение не отменяет single-image benchmark gate #630.
- `LOCAL_UNCENSORED` и `CLOUD_PRO` не затрагиваются.
- Full archive не становится mass VL backfill и не меняет Storage eligibility/encryption/size policy.
- Production deploy и переключение feature flags выполняются отдельно после merge и подтверждённого image provenance.

## Проверки

Regression coverage проверяет:

1. выключенный full-archive не блокирует VL;
2. остаточный Storage backlog держит gate закрытым даже без текущего running job;
3. gate открывается после исчерпания backlog;
4. invalid Librarian configuration блокирует VL fail-closed;
5. VL consumer при Arthur priority не вызывает `claim_next` и не запускает processor;
6. после снятия priority consumer claim-ит и завершает ровно одну VL task.

## После merge

Перед production activation всё ещё требуется завершить канонический `512 / 1` LOCAL_MAIN acceptance. После acceptance целевая эксплуатация: Arthur full-archive может оставаться включённым; автоматическая Qwen image queue сама ждёт его полного завершения и стартует после открытия DB-backed priority gate.
