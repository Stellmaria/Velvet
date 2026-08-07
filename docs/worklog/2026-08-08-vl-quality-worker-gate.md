# VL quality worker production gate

- Дата: 2026-08-08
- ID: `2026-08-08-vl-quality-worker-gate`
- Линия/фаза: Velvet AI / Qwen, production hotfix / эксплуатационная стабилизация
- Статус: `частично`
- Ветка: `fix/vl-quality-worker-gate-v2`
- Базовый commit: `8e77885c676c51fbae49e513c28265e8a45b7e47`

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
- передавать состояние gate из composition в quality service, не делать новый env-read внутри domain service;
- не менять interactive/workspace/semantic VL routes этим hotfix;
- обновить server/local-VL env examples;
- добавить regression test на fail-closed execution и env defaults;
- сохранить package-architecture baseline без нового debt fingerprint;
- зафиксировать фактические проверки и CI evidence до merge.

### Критерии готовности

- при отсутствующем/false `AI_QUALITY_ENABLED` periodic вызов `ai-quality` завершается до provider check и до `claim_targets`, поэтому не создаёт quality workload;
- при `AI_QUALITY_ENABLED=true` service выполняет прежний quality path;
- workspace quality и semantic vision worker новым gate не отключаются;
- env examples явно содержат fail-closed default;
- required CI проходит;
- production smoke остаётся отдельным live-обязательством после deployment.

### Риски и ограничения

- worker остаётся зарегистрирован в WorkerManager и делает дешёвый no-op каждые 10 секунд при выключенном gate; это не создаёт inference/DB claim;
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

- `AI_QUALITY_ENABLED` читается существующим composition helper `_env_enabled()` и передаётся в `CalibratedAIQualityService` как `background_enabled`;
- `CalibratedAIQualityService` сохраняет explicit boolean policy и при выключенном gate возвращает `0` до `_provider_available()` и repository `claim_targets()`;
- background worker поэтому не инициирует inference и не запускает автоматический claim/seed quality targets при общем `AI_VISION_ENABLED=true`;
- существующий `ai-quality` registry, worker interval и local AI lock сохранены;
- `.env.server.example` и `.env.vision-local.example` фиксируют `AI_QUALITY_ENABLED=false`;
- добавлен `tests/test_vl_quality_worker_gate.py`, проверяющий no-op до provider/repository и fail-closed env defaults;
- первоначальный PR #706 закрыт без merge после движения `main`; реализация пересобрана поверх актуального `main` в PR #709.

### Миграции и совместимость

Миграций PostgreSQL нет. Существующие quality rows/results не меняются. При явном `AI_QUALITY_ENABLED=true` periodic worker использует прежний service/client/repository path. Semantic VL queue и workspace quality сохраняют прежнюю регистрацию. Изменение требует restart/recreate bot process после обновления env, поскольку состояние gate передаётся при composition.

### Проверки

- PR #709 на предыдущем head: project notes contract #3479, type check #3192, tests #4548, security supply chain #1175, docker build #3679 и branch protection contract #967 прошли успешно;
- ветка затем перебазирована на актуальный `main` без пересекающихся изменений; required CI должен повторно подтвердить итоговый merge candidate;
- live production smoke не выполнен и остаётся отдельным обязательством после deployment.

### PR и commit

- superseded PR: #706, закрыт без merge;
- final PR: #709 `Gate background VL quality worker`;
- ветка: `fix/vl-quality-worker-gate-v2`;
- final merge SHA будет зафиксирован GitHub после merge.

### Незавершённое

- получить зелёный required CI на актуальной базе и слить PR #709;
- выполнить live deployment smoke после merge;
- отдельным slice исправить quality output/retry/cancel/backfill policy;
- после safety slices реализовать 3-model routing contract из #630.

### Следующий шаг

После зелёного required CI слить PR #709. Затем перейти к bounded quality pipeline hotfix из #630.
