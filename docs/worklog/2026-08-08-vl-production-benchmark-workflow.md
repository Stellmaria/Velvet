# VL production benchmark workflow

- Дата: 2026-08-08
- ID: `2026-08-08-vl-production-benchmark-workflow`
- Линия/фаза: Velvet AI / VL, Phase 0 production benchmark execution boundary
- Статус: `частично`
- Ветка: `feat/vl-production-benchmark-workflow`
- Базовый commit: `8ff8cbf688c7c47e6c4fb585ec37d7ccf59ea855`

Связано: #630, #732, #727, #709, #712, #718.

## Перед началом

### Цель

Дать owner безопасный и аудируемый production entrypoint для уже merged `scripts/benchmark_vision_gateway.py`, не публикуя vision-gateway наружу, не выдавая bot Docker socket и не смешивая benchmark с archive/global quality lifecycle.

### Исходный контекст

PR #732 закрепил production `LOCAL_MAIN=qwen3.5:9b`, digest prefix `6488c96fa5fa` и benchmark scorecard contract. GitHub connector текущей сессии умеет читать/писать repository и CI, но не предоставляет workflow-dispatch action и прямого SSH/VPS execution tool.

Production deployment уже использует GitHub Environment `production` и SSH secrets `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_PORT`, `DEPLOY_APP_DIR`, `DEPLOY_SSH_KEY`, `DEPLOY_KNOWN_HOSTS`. Поэтому bounded benchmark должен переиспользовать эту boundary, а не добавлять новый доступ к VPS.

### Планируемый объём

- добавить только manual `workflow_dispatch` production workflow;
- требовать exact `main` source commit, уже развернутый и clean на VPS;
- разрешать только closed-set image basename из `<VELVET_DATA_DIR>/runtime/vision-benchmark/`;
- разрешать caps только `384 / 512 / 768` и rounds только `1 / 3 / 5`;
- default оставить один sample и без cold unload;
- fail-closed проверять global quality/queue/optional route gates, model/digest/concurrency/timeout;
- использовать уже работающие bot/runtime/gateway containers, ничего не start/restart/pull;
- запускать host benchmark через internal gateway и забирать только JSON scorecard artifact;
- не загружать source image в GitHub artifact;
- добавить regression contract на эти ограничения.

### Критерии готовности

- workflow не имеет `push`/`pull_request` trigger;
- execution возможен только на `main`, с confirmation `BENCHMARK` и exact source SHA;
- remote checkout обязан быть `main`, exact SHA и clean;
- benchmark отказывается работать при включенном global quality, semantic queue, CLOUD_PRO или LOCAL_UNCENSORED;
- model identity `qwen3.5:9b` / `6488c96fa5fa`, concurrency `1`, timeout `300` проверяются до inference;
- image path нельзя вывести из закрытого benchmark directory через input;
- workflow не выполняет compose up/pull/restart и не enqueue-ит archive work;
- artifact содержит только `benchmark.json`;
- required CI проходит на final head.

### Риски и ограничения

- workflow не деплоит #732/#733 сам: production checkout должен уже быть exact `source_commit`, иначе run fail-closed;
- workflow не создаёт evaluation image и не выбирает его содержимое;
- один run измеряет один output cap; для matrix 384/512/768 нужны отдельные explicit owner dispatches;
- `cold_unload=true` является отдельным явным выбором, потому что выгружает warm LOCAL_MAIN перед sample 1;
- benchmark создаёт реальную CPU inference load и поэтому сериализован общей production concurrency group;
- GitHub connector этого чата не умеет dispatch workflow, поэтому live acceptance останется отдельным шагом после merge;
- никакой mass backfill или controlled batch этим slice не разрешается.

### Стабилизационный допуск

1. Новый workflow является operational boundary существующего benchmark, а не новой продуктовой функцией.
2. Production access переиспользует существующие environment secrets и SSH trust chain.
3. Сетевой surface не расширяется.
4. All dangerous AI gates проверяются fail-closed до inference.
5. Source image не покидает VPS через workflow artifact.

## После завершения

### Фактически сделано

- добавлен `.github/workflows/production-vl-benchmark.yml` с manual-only dispatch;
- workflow требует `BENCHMARK`, exact executing main SHA и already-deployed clean remote checkout;
- input image ограничен basename JPEG/PNG/WebP в `runtime/vision-benchmark`;
- output cap ограничен 384/512/768, samples — 1/3/5, default — 512 и один sample;
- cold unload по умолчанию выключен и включается отдельным boolean input;
- перед inference проверяются `AI_QUALITY_ENABLED=false`, `AI_VISION_QUEUE_ENABLED=false`, `CLOUD_PRO=false`, `LOCAL_UNCENSORED=false`, canonical model/digest, concurrency=1 и timeout=300;
- workflow использует только уже работающие bot/runtime/gateway containers и existing host harness;
- в GitHub возвращается только `benchmark.json` и bounded Step Summary;
- добавлен `tests/test_production_vl_benchmark_workflow.py` с manual-only, policy, bounds и no-mutation contracts.

### Миграции и совместимость

DB migration нет. Production flags, containers, model volume и quality queues workflow не изменяет. Existing deploy workflow/secrets используются без новых credentials.

### Проверки

Required CI должен подтвердить workflow syntax/security/action-pin/test contracts на финальном head. Live workflow dispatch этим code PR не выполняется.

### PR и commit

- branch: `feat/vl-production-benchmark-workflow`;
- PR создаётся после завершения bounded workflow/test/worklog slice;
- exact green head и merge SHA фиксируются перед merge.

### Незавершённое

- получить required green CI и исправить только реальные regressions;
- при движении `main` пересобрать exact tree поверх нового head и прогнать CI заново;
- слить только `behind_by=0` exact green head;
- после deploy exact merged commit owner должен вручную dispatch первый run с `rounds=1`, `output_cap=512`, `cold_unload=false`;
- только после успешного first smoke выполнять cold/warm и cap matrix;
- controlled batch 10 остаётся запрещён до сохранённого benchmark evidence и owner quality review.

### Следующий шаг

После merge и deployment exact commit выполнить first production single-image smoke через workflow, скачать scorecard artifact и заполнить manual quality fields до любого batch rollout.
