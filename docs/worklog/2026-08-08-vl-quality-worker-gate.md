# VL quality worker production gate

- Дата: 2026-08-08
- ID: `2026-08-08-vl-quality-worker-gate`
- Линия/фаза: Velvet AI / Qwen, production hotfix / эксплуатационная стабилизация
- Статус: `частично`
- Ветка: `fix/vl-quality-worker-gate`
- Базовый commit: `328749227e26a8bfc8fc39447bf9782b9b040f2a`

Связано: #630, #410, #416, #421.

## Перед началом

### Цель

Остановить неявный фоновый `ai-quality` workload при обычном `AI_VISION_ENABLED=true` и отделить возможность использовать VL от разрешения фоновой глобальной проверки качества.

### Исходный контекст

Production-диагностика 2026-08-07 показала CPU-only `qwen3.5:9b` на 8 vCPU VPS: около 6 CPU, около 10.4 ГБ RAM и длительные запросы, упирающиеся в 300-second timeout. В `media_ai_quality_checks` на момент диагностики было 1779 `ready`, 24 `pending`, 3 `processing`, 2 `error`, 10 `skipped`. `workspace_qwen_checks` активного backlog не имел.

В базовом `main` `velvet_bot/app/workers.py` регистрировал `ai-quality` всякий раз, когда включён общий `AI_VISION_ENABLED`; отдельного production gate для фонового quality worker не было. Это позволяло background quality workload стартовать независимо от явного решения владельца.

### Планируемый объём

- добавить отдельный fail-closed env gate `AI_QUALITY_ENABLED` для periodic `ai-quality` worker;
- default оставить `false`;
- не менять interactive/workspace/semantic VL routes этим hotfix;
- обновить server/local-VL env examples;
- добавить regression test на наличие gate и fail-closed defaults;
- зафиксировать фактические проверки и CI evidence до merge.

### Критерии готовности

- при отсутствующем/false `AI_QUALITY_ENABLED` worker `ai-quality` не регистрируется;
- при `AI_QUALITY_ENABLED=true` worker регистрируется как раньше;
- workspace quality и semantic vision worker не отключаются новым gate;
- env examples явно содержат fail-closed default;
- required CI проходит;
- production smoke остаётся отдельным live-обязательством после deployment.

### Риски и ограничения

- hotfix не меняет текущий quality JSON token budget и timeout policy;
- hotfix не удаляет существующие строки `media_ai_quality_checks` и не меняет решения;
- ручные quality operations вне periodic worker этим изменением не перепроектируются;
- следующий slice отдельно исправляет output/retry/cancel/backfill semantics и затем реализует 3-model router из #630;
- изменение не объявляется production-accepted до live deployment smoke.

### Стабилизационный допуск

1. Улучшается существующая функция AI quality, новая предметная область не добавляется.
2. Управляемость и надёжность повышаются: VL можно держать включённым без автоматического фонового global quality workload.
3. Предметные границы архива не меняются.
4. Улучшение проверяется regression test и CI, затем live worker/process evidence.
5. Сохраняются `vision-gateway`, WorkerManager, repository/service boundaries и общий local inference lock.

## После завершения

### Фактически сделано

- periodic `ai-quality` worker помещён за отдельный `AI_QUALITY_ENABLED` gate;
- `CalibratedAIQualityService` для этого worker создаётся только при явном включении gate;
- общий `AI_VISION_ENABLED` больше не является достаточным условием для регистрации global quality worker;
- `.env.server.example` и `.env.vision-local.example` фиксируют `AI_QUALITY_ENABLED=false`;
- добавлен `tests/test_vl_quality_worker_gate.py` с source-contract проверкой gate и env defaults.

### Миграции и совместимость

Миграций PostgreSQL нет. Существующие quality rows/results не меняются. При явном `AI_QUALITY_ENABLED=true` periodic worker сохраняет прежний service/client/repository path. Semantic VL queue и workspace quality сохраняют прежнюю регистрацию.

### Проверки

- `type check` run #3161: success на head `bfe6c42ad8bec608461b7a9cf08c8152d313cb57`;
- первый `project notes contract` run #3451 выявил несоответствие формату worklog; запись исправлена этим commit;
- остальные required CI checks ожидаются на новом head;
- live production smoke не выполнен и остаётся отдельным обязательством после deployment.

### PR и commit

- PR: #706 `Gate background VL quality worker`;
- implementation head до исправления worklog: `bfe6c42ad8bec608461b7a9cf08c8152d313cb57`;
- final commit и merge SHA будут дописаны после зелёного CI/merge.

### Незавершённое

- дождаться повторного required CI на исправленном worklog;
- выполнить live deployment smoke после merge;
- отдельным slice исправить quality output/retry/cancel/backfill policy;
- после safety slices реализовать 3-model routing contract из #630.

### Следующий шаг

Получить зелёный required CI для PR #706, при необходимости устранить обнаруженные regression/architecture inventory failures, завершить worklog и слить PR. Затем перейти к bounded quality pipeline hotfix из #630.
