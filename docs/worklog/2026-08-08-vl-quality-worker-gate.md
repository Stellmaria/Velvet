# 2026-08-08 — VL quality worker production gate

Статус: частично

Линия: Velvet AI / Qwen, production hotfix / эксплуатационная стабилизация.

Связано: #630, #410, #416, #421.

## Перед началом

### Цель

Остановить неявный фоновый `ai-quality` backfill при обычном `AI_VISION_ENABLED=true` и отделить возможность использовать VL от разрешения массовой фоновой проверки качества.

### Исходный контекст

Production-диагностика 2026-08-07 показала CPU-only `qwen3.5:9b` на 8 vCPU VPS: около 6 CPU, около 10.4 ГБ RAM и длительные запросы, упирающиеся в 300-second timeout. В `media_ai_quality_checks` на момент диагностики было 1779 `ready`, 24 `pending`, 3 `processing`, 2 `error`, 10 `skipped`. `workspace_qwen_checks` активного backlog не имел.

В current `main` `velvet_bot/app/workers.py` регистрирует `ai-quality` всякий раз, когда включён общий `AI_VISION_ENABLED`; отдельного production gate для фонового quality worker нет. Это позволяет background quality workload стартовать независимо от явного решения владельца на mass/backfill processing.

### Планируемый объём

- добавить отдельный fail-closed env gate `AI_QUALITY_ENABLED` для periodic `ai-quality` worker;
- default оставить `false`;
- не менять interactive/workspace/semantic VL routes этим hotfix;
- обновить server/local-VL env examples;
- добавить regression test на default-off и explicit-on регистрацию worker;
- зафиксировать фактические проверки и CI evidence до merge.

### Критерии готовности

- при `AI_VISION_ENABLED=true` и отсутствующем/false `AI_QUALITY_ENABLED` worker `ai-quality` не регистрируется;
- при `AI_QUALITY_ENABLED=true` worker регистрируется как раньше;
- workspace quality и semantic vision worker не отключаются новым gate;
- env examples явно содержат fail-closed default;
- required CI проходит;
- production smoke остаётся отдельным live-обязательством после deployment.

### Риски и ограничения

- hotfix не меняет текущий quality JSON token budget и timeout policy;
- hotfix не удаляет уже существующие строки `media_ai_quality_checks` и не меняет их решения;
- ручные операции, которые явно запускают quality service вне periodic worker, этим изменением не должны скрыто превращаться в mass backfill;
- следующий slice должен отдельно исправить output/retry/cancel/backfill semantics и затем реализовать 3-model router из #630;
- изменение не объявляется production-accepted до live deployment smoke.

### Стабилизационный допуск

1. Улучшается существующая функция AI quality, а не добавляется новая предметная область.
2. Управляемость и надёжность повышаются: VL можно держать включённым без автоматического фонового quality workload.
3. Предметные границы архива не меняются.
4. Улучшение проверяется worker-registry regression test и CI, затем live worker/process evidence.
5. Сохраняются `vision-gateway`, WorkerManager, repository/service boundaries и общий local inference lock.

### База

- base commit: `328749227e26a8bfc8fc39447bf9782b9b040f2a`;
- branch: `fix/vl-quality-worker-gate`;
- canonical VL plan: issue #630.

## После завершения

Будет заполнено после реализации и CI. До этого статус остаётся `частично`.
