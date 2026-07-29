# 2026-07-28 — пакетная очередь semantic VL

- Дата: 2026-07-28
- ID: ai-vision-batch-queue
- Линия/фаза: Линия B — Velvet AI / batch queue
- Статус: `частично`
- Ветка: `agent/ai-vision-batch-queue`
- Базовый commit: `de9d59441aabbae1c888da65be26932588fd62e4`

## Перед началом

### Цель

Добавить постоянный план пакетного semantic VL-анализа с максимальной оценкой расходов до запуска, отдельным owner-подтверждением и queue consumer, который обрабатывает задачи через существующий Flash → Pro → sensitive router.

### Исходный контекст

После PR #352 смысловой VL-анализ имеет каскад, транзакционный budget executor и PostgreSQL-кэш. После PR #353 таблица `ai_tasks` имеет атомарный lifecycle, dedupe, retry/backoff и owner-наблюдаемость. Semantic worker пока продолжает напрямую опрашивать `media_ai_profiles`, поэтому владелец не может заранее увидеть стоимость партии и подтвердить её запуск как единое действие.

### Планируемый объём

- добавить таблицу постоянных batch-планов со сроком действия и статусами;
- выбирать кандидатов semantic VL из существующего media/profile каталога без блокировки worker;
- рассчитывать консервативную максимальную стоимость одного изображения и всей партии;
- сравнивать план с доступным дневным, месячным и per-request бюджетом;
- добавить `/ai_batch_plan`, `/ai_batch_start`, `/ai_batch_status`, `/ai_batch_cancel`;
- запускать партию только по UUID подтверждённого плана;
- ставить задачи в `ai_tasks` с dedupe key по media ID и prompt version;
- добавить queue consumer для `vision.semantic-profile`;
- сохранять result/task linkage и использовать существующий cascade/cache;
- оставить direct semantic polling как rollback-режим через feature flag;
- добавить PostgreSQL integration и Telegram formatting/access tests.

### Критерии готовности

- создание плана не выполняет provider calls и не резервирует токены;
- план показывает candidate count, max cost per item, total max и доступный бюджет;
- превышающий бюджет план нельзя запустить;
- истёкший или отменённый план нельзя запустить;
- повторный `/ai_batch_start UUID` не создаёт дубли;
- consumer атомарно claim задачу, обрабатывает один media ID и завершает либо retry/error через queue lifecycle;
- cache hit завершает task без нового provider call;
- при queue mode direct semantic polling не конкурирует с queue consumer;
- tests, type check, Docker build, notes contract и backup restore drill проходят.

### Риски и ограничения

- предварительная оценка консервативна и может быть выше фактической стоимости;
- фактические model ID и pricing подтверждаются только живым API-тестом;
- batch progress UI ограничивается counts, полноценная progress-card остаётся следующим улучшением;
- quality/workspace-Qwen задачи в этот batch не входят;
- applied migrations не редактируются, используется новая `z008`.

## После завершения

### Фактически сделано

- добавлены `VisionBatchPlan`, статусы и progress-модель;
- добавлен PostgreSQL repository для выбора до 5000 кандидатов, планов, запуска, отмены и progress;
- добавлена консервативная оценка полного настроенного каскада Flash → Pro → sensitive;
- перед стартом повторно проверяются дневной, обычный месячный и per-request лимиты;
- созданные queue-задачи содержат `media_id`, `prompt_version` и `batch_id`;
- миграционный trigger переносит `batch_id` из payload в FK атомарно при queue insert;
- добавлен targeted semantic processor и queue consumer с heartbeat;
- при `AI_VISION_QUEUE_ENABLED=true` direct semantic polling заменяется consumer, при `false` сохраняется прежний rollback-путь;
- добавлены owner-only команды планирования, подтверждения, статуса и отмены;
- команды включены в полный owner help/access contract;
- добавлены unit и PostgreSQL integration tests;
- `.env.example` получил queue feature flag и TTL подтверждения.

### Миграции и совместимость

Добавлена миграция `z008_ai_vision_batches.sql`. Она создаёт `ai_task_batches`, добавляет nullable `ai_tasks.batch_id`, индексы и безопасный trigger привязки задачи к партии. Queue mode по умолчанию выключен и не меняет production-поведение до явного включения.

### Проверки

CI ещё выполняется. Обязательны полный tests workflow, type check, Docker build, project notes contract и backup restore drill.

### PR и commit

- PR: #354, draft до полного зелёного CI.
- Ветка: `agent/ai-vision-batch-queue`.

### Незавершённое

- исправить замечания CI, если появятся;
- зафиксировать точные номера зелёных workflow runs;
- снять draft и выполнить squash merge;
- после merge перейти к серверному Compose/readiness.

### Следующий шаг

Запустить полный CI по итоговому head, исправить реальные failures и только после пяти зелёных ворот слить PR #354.
