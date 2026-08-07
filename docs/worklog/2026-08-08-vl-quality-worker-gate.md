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

В базовом `main` periodic `ai-quality` запускался всякий раз, когда был включён общий `AI_VISION_ENABLED`; отдельного production gate для фактической фоновой quality-обработки не было. Это позволяло background quality workload стартовать независимо от явного решения владельца.

### Планируемый объём

- добавить отдельный fail-closed env gate `AI_QUALITY_ENABLED` для фактического выполнения periodic `ai-quality` processing;
- default оставить `false`;
- не менять interactive/workspace/semantic VL routes этим hotfix;
- обновить server/local-VL env examples;
- добавить regression test на fail-closed execution и env defaults;
- сохранить существующий WorkerManager registry fingerprint, чтобы hotfix не обновлял архитектурное исключение монолитной composition-функции;
- зафиксировать фактические проверки и CI evidence до merge.

### Критерии готовности

- при отсутствующем/false `AI_QUALITY_ENABLED` periodic вызов `ai-quality` завершается до provider check и до `claim_targets`, поэтому не создаёт quality workload;
- при `AI_QUALITY_ENABLED=true` service выполняет прежний quality path;
- workspace quality и semantic vision worker новым gate не отключаются;
- env examples явно содержат fail-closed default;
- required CI проходит;
- production smoke остаётся отдельным live-обязательством после deployment.

### Риски и ограничения

- worker остаётся зарегистрирован в WorkerManager и делает дешёвый no-op каждые 10 секунд при выключенном gate; это намеренно сохраняет существующий architecture fingerprint и не создаёт inference/DB claim;
- hotfix не меняет текущий quality JSON token budget и timeout policy;
- hotfix не удаляет существующие строки `media_ai_quality_checks` и не меняет решения;
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

- `CalibratedAIQualityService` при создании фиксирует fail-closed состояние `AI_QUALITY_ENABLED`;
- при выключенном gate `process_once()` возвращает `0` до `_provider_available()` и до repository `claim_targets()`, поэтому background worker не инициирует inference и не засеивает/забирает quality targets;
- существующий `ai-quality` registry в `velvet_bot/app/workers.py` оставлен без изменения, чтобы не менять уже зарегистрированный monolithic-function architecture fingerprint;
- `.env.server.example` и `.env.vision-local.example` фиксируют `AI_QUALITY_ENABLED=false`;
- добавлен `tests/test_vl_quality_worker_gate.py`, проверяющий no-op до provider/repository и parsing/default gate.

### Миграции и совместимость

Миграций PostgreSQL нет. Существующие quality rows/results не меняются. При явном `AI_QUALITY_ENABLED=true` periodic worker использует прежний service/client/repository path. Semantic VL queue и workspace quality сохраняют прежнюю регистрацию. Изменение требует restart/recreate bot process после обновления env, поскольку состояние gate фиксируется при создании service.

### Проверки

- `type check` run #3161: success на раннем implementation head;
- `project notes contract` run #3452: success после приведения worklog к обязательному формату;
- ранний tests run #4517 выявил stale `velvet_bot/app/workers.py` architecture fingerprint; изменение WorkerManager было откачено, gate перенесён в bounded `CalibratedAIQualityService`;
- required CI на итоговом head ожидается;
- live production smoke не выполнен и остаётся отдельным обязательством после deployment.

### PR и commit

- PR: #706 `Gate background VL quality worker`;
- текущая реализация развивается в `fix/vl-quality-worker-gate`;
- final commit и merge SHA будут дописаны после зелёного CI/merge.

### Незавершённое

- дождаться required CI на итоговом head и устранить только подтверждённые failures;
- выполнить live deployment smoke после merge;
- отдельным slice исправить quality output/retry/cancel/backfill policy;
- после safety slices реализовать 3-model routing contract из #630.

### Следующий шаг

Получить зелёный required CI для PR #706, завершить worklog evidence и слить PR. Затем перейти к bounded quality pipeline hotfix из #630.
