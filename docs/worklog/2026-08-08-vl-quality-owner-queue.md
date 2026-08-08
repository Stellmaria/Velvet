# VL quality owner-controlled queue

- Дата: 2026-08-08
- ID: `2026-08-08-vl-quality-owner-queue`
- Линия/фаза: Velvet AI / Qwen, production safety / owner-controlled quality queue
- Статус: `частично`
- Ветка: `feat/vl-quality-owner-queue`
- Базовый commit: `8b160db820592c36f51da491b0525754f6954bdf`

Связано: #630, #709, #712, #421.

## Перед началом

### Цель

Заменить немедленную постановку global quality backlog и массовый retry на fail-closed lifecycle `plan -> explicit start`, чтобы включение `AI_QUALITY_ENABLED` само по себе не могло оживить старую или случайно созданную очередь архива.

### Исходный контекст

PR #709 добавил fail-closed `AI_QUALITY_ENABLED=false`, а PR #712 ограничил quality output до 512 tokens и убрал implicit `all media_files -> pending` из `AIQualityRepository.claim_targets()`. При этом в production уже существовал legacy backlog, а owner-кнопки `Последние` и `Повтор ошибок` всё ещё напрямую меняли global quality queue. Старый `retry_errors()` дополнительно сбрасывал semantic `media_ai_profiles`, смешивая два независимых контура.

Канонический план #630 требует controlled rollout `10 -> 25 -> 100`, explicit owner approval и запрет mass backfill до evidence. Поэтому следующий bounded slice должен дать точный dry-run plan, отдельное подтверждение и provenance каждой global quality queue row.

### Планируемый объём

- добавить persistent `media_ai_quality_queue_plans` с owner, exact `media_ids`, limit, breakdown, expiry и start evidence;
- добавить `media_ai_quality_checks.queue_plan_id` как provenance queue row;
- карантинировать pre-plan active legacy global quality backlog;
- заменить immediate recent enqueue на `plan_recent()` + `start_plan()`;
- заменить global quality+semantic `retry_errors()` на quality-only error plan;
- сохранить старые callback action names ради совместимости существующих Telegram menu links;
- дать owner controlled sizes 10, 25 и 100;
- не включать `AI_QUALITY_ENABLED` и не запускать batch этим PR;
- покрыть dry-run, exact-id start, owner isolation, migration quarantine и PostgreSQL semantic isolation тестами.

### Критерии готовности

- создание плана не изменяет `media_ai_quality_checks`;
- план хранит конечный exact набор media IDs и живёт ограниченное время;
- start возможен только создавшим план owner, один раз и до expiry;
- start не пересчитывает candidates и не может незаметно расширить batch;
- legacy `pending`, `processing` и `error` без plan provenance не остаются автоматически runnable;
- existing `ready` reports и owner decisions сохраняются;
- quality error retry больше не мутирует `media_ai_profiles`;
- Telegram UI требует отдельное подтверждение после plan preview;
- required CI зелёный на финальном head.

### Риски и ограничения

- migration сознательно переводит legacy active global quality rows без provenance в `skipped`; это fail-closed quarantine, а не удаление данных;
- quarantined rows остаются видимы и могут быть явно выбраны новым controlled plan;
- existing explicit single-media `AIQualityRepository.retry(media_id)` остаётся отдельным owner action и не превращается в mass path;
- `AI_QUALITY_ENABLED=false` остаётся production default до отдельного single-target smoke;
- этот slice не меняет transport timeout/cancel/OOM semantics и не реализует 3-model runtime switching;
- controlled plan start только формирует очередь, но не является разрешением на mass rollout beyond 10 -> 25 -> 100 gates.

### Стабилизационный допуск

1. Новая предметная область не добавляется: меняется только lifecycle существующей global quality queue.
2. Изменение уменьшает blast radius и добавляет явную owner authorization boundary.
3. Existing `AIQualityRepository` worker boundary сохраняется.
4. Migration сохраняет ready/history data и только карантинирует непроверяемый active backlog.
5. Каждый массовый start ограничен exact persisted ids и размером до 100.

## После завершения

### Фактически сделано

- добавлен `QualityQueuePlan` и repository lifecycle `plan_recent`, `plan_errors`, `get_plan`, `start_plan`;
- plan сохраняет owner, exact media IDs, requested limit, breakdown `new / legacy_pending / failed`, 15-minute expiry, `started_at` и `started_count`;
- planning является dry-run для quality queue и не вставляет/не обновляет `media_ai_quality_checks`;
- `start_plan()` использует только persisted `media_ids`, требует того же owner, блокирует expired/already-started plan и пишет `queue_plan_id`;
- recent quality UI теперь предлагает controlled plan sizes 10 / 25 / 100 и отдельный confirmation screen;
- error retry UI создаёт quality-only plan вместо немедленного сброса всех quality и semantic errors;
- старые callback action names `quality_recent` и `quality_retry_errors` сохранены, но их semantics стали plan-only;
- добавлен отдельный `quality_plan_start` callback для явного запуска;
- `quality_run` остался отдельным действием и запускает только один worker cycle;
- semantic `media_ai_profiles` больше не изменяются из global quality retry control.

### Миграции и совместимость

Добавлена `migrations/zz002_quality_owner_queue.sql`. Она создаёт `media_ai_quality_queue_plans`, добавляет nullable `queue_plan_id` и FK/indexes в `media_ai_quality_checks`. Все pre-plan rows с `queue_plan_id IS NULL` и status `pending`, `processing` или `error` переводятся в `skipped` с диагностическим сообщением. Это intentionally fail-closed quarantine: rows не удаляются, `ready` результаты и owner decisions не меняются. После migration owner может явно вернуть нужные quarantined rows через новый plan/start flow.

### Проверки

- добавлен `tests/test_vl_quality_owner_queue.py`: dry-run planning, exact persisted ids, wrong-owner failure и migration quarantine contract;
- `tests/test_qwen_duplicate_retry_controls.py` обновлён под quality-only plan и проверяет отсутствие semantic mutation;
- `tests/test_quality_retry_postgres.py` теперь проверяет PostgreSQL isolation: quality row переводится в controlled pending, semantic error/profile остаётся без изменений;
- `tests/test_p2b_quality_callback_ack.py` обновлён для plan/render/start acknowledgement ordering;
- initial type check на PR #718 прошёл;
- initial project notes contract выявил неверный формат worklog; этот commit приводит worklog к canonical project-notes template;
- остальные required CI должны пройти на финальном head до merge.

### PR и commit

- PR: #718 `Gate VL quality backfill behind owner plans`;
- branch: `feat/vl-quality-owner-queue`;
- merge SHA будет добавлен GitHub после зелёного CI/merge.

### Незавершённое

- получить зелёный required CI и слить PR #718;
- оставить production `AI_QUALITY_ENABLED=false` до явного single-target smoke;
- выполнить production migration/deploy acceptance и подтвердить отсутствие самопроизвольных global claims;
- следующим отдельным slice реализовать typed timeout/cancel/OOM/retry semantics;
- затем продолжить 3-model routing по #630.

### Следующий шаг

Дождаться required CI на исправленном head, исправить любые реальные regressions и слить PR #718 только при зелёных проверках. После merge не запускать mass backfill: первый production enable остаётся single-target smoke, затем controlled evidence `10 -> 25 -> 100`.
