# 2026-07-29 — пакетная очередь semantic VL после Kie merge

- Дата: 2026-07-29
- ID: ai-vision-batch-queue-v2
- Линия/фаза: Линия B — Velvet AI / batch queue
- Статус: `частично`
- Ветка: `agent/ai-vision-batch-queue-v2`
- Базовый commit: `574291c46e262452d76cd66ac1416cd660a4c4fb`

## Перед началом

### Цель

Перенести готовую реализацию подтверждаемых semantic VL-партий на актуальный `main` после слияния PR #355, сохранив Kie media generation, интерфейс «Мяу» и единый PostgreSQL lifecycle AI-задач.

### Исходный контекст

PR #354 был создан до слияния Kie-контура и пересёкся с ним в `workers.py`, `.env.example` и owner-интерфейсе. Автоматическое слияние стало небезопасным: слепое разрешение конфликта могло удалить Kie worker либо batch consumer. Поэтому создана новая ветка от commit `574291c`, а batch-функциональность перенесена и объединена вручную.

### Планируемый объём

- перенести модели, storage, service и consumer VL-партий;
- сохранить Kie worker `media.generate.kie` и добавить consumer `vision.semantic-profile`;
- добавить постоянные batch-планы с UUID, сроком действия и progress;
- рассчитывать консервативный максимум полной настроенной цепочки Flash → Pro → sensitive;
- повторно проверять дневной, месячный и per-request бюджеты перед стартом;
- оставить queue mode выключенным по умолчанию;
- объединить `.env.example`, owner help и access contract с Kie-контуром;
- добавить unit и PostgreSQL integration tests;
- закрыть старый конфликтующий PR #354 после открытия заменяющего PR.

### Критерии готовности

- Kie и VL batch workers одновременно присутствуют в worker registry;
- direct semantic polling выключается только при `AI_VISION_QUEUE_ENABLED=true`;
- планирование не выполняет provider calls;
- запуск требует отдельного UUID-подтверждения;
- queue task получает `batch_id` атомарно при insert;
- прерванный старт восстанавливается без orphan tasks;
- отмена снимает ожидающие задачи партии;
- progress переводит полностью завершённую партию в `completed`;
- tests, type check, Docker build, notes contract и backup restore drill проходят.

### Риски и ограничения

- живые model ID и цены всё ещё требуют server smoke-test;
- queue mode остаётся `false` до проверки на VPS;
- running provider request нельзя физически отозвать после отправки;
- progress пока текстовый, без редактируемой Telegram-карточки;
- quality и workspace-Qwen не переводятся в эту партию.

## После завершения

### Фактически сделано

- создана новая ветка от актуального `main` с уже слитым Kie;
- перенесены `vision_batches` models/store/service/worker;
- Kie worker и VL batch consumer объединены в одном registry с разными task types;
- добавлены owner-команды `/ai_batch_plan`, `/ai_batch_start`, `/ai_batch_status`, `/ai_batch_cancel`;
- добавлена миграция `z008_ai_vision_batches.sql` с FK и trigger привязки `batch_id` из payload;
- добавлены stale-start recovery и self-healing progress;
- `.env.example` сохраняет Kie-настройки и добавляет queue flag/TTL;
- command/access/help contracts обновлены без удаления существующего интерфейса;
- добавлены unit и PostgreSQL integration tests;
- generated navigation inventory обновлён с учётом Kie и семи новых Python-файлов.

### Миграции и совместимость

Добавляется только новая миграция `z008_ai_vision_batches.sql`. Existing Kie и AI queue tables не изменяются разрушительно. `ai_tasks.batch_id` nullable; старые задачи продолжают работать. `AI_VISION_QUEUE_ENABLED=false` сохраняет прежний direct polling как rollback.

### Проверки

CI ещё не запущен для итогового объединённого head. Обязательны полный tests workflow, type check, Docker build, project notes contract и backup restore drill.

### PR и commit

- Новый PR будет открыт после проверки diff.
- Старый PR #354 будет закрыт как superseded после открытия замены.

### Незавершённое

- открыть draft PR от `agent/ai-vision-batch-queue-v2`;
- исправить возможные failures после Kie merge;
- зафиксировать точные workflow runs;
- выполнить squash merge;
- перейти к `server-production-readiness`.

### Следующий шаг

Проверить объединённый diff, открыть заменяющий draft PR и прогнать пять обязательных CI-ворот.
