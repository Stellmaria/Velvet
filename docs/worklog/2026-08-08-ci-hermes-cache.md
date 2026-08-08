# CI Hermes cache and Docker gate latency

- Дата: 2026-08-08
- ID: ci-hermes-cache-20260808
- Линия/фаза: CI / merge latency optimization
- Статус: частично
- Ветка: perf/hermes-ci-cache
- Базовый commit: 42bd97eedd0807befb92cfcd56cd231e9cc51567

## Перед началом

### Цель

Сократить остаточную задержку protected CI после параллелизации Docker surfaces без ослабления required checks, security coverage или production Docker semantics.

### Исходный контекст

- PR #720 уже разнёс Velvet, Supervisor, Vision, Krita и Hermes по независимым jobs;
- исторически Hermes `docker compose build` занимал основную часть Docker critical path;
- `deploy/hermes-coders/compose.yaml` использует один `Dockerfile.coder` для четырёх сервисных image tags и один `Dockerfile.db-proxy` для двух DB proxy tags;
- остальные Docker CI builds уже используют Buildx GitHub Actions cache;
- `docker-build-contract` ждёт финальный check `build` polling-циклом с интервалом 15 секунд.

### Планируемый объём

- собирать Hermes coder Dockerfile один раз и назначать все четыре существующих tags;
- собирать Hermes DB proxy Dockerfile один раз и назначать оба существующих tags;
- использовать отдельные GHA cache scopes для coder и DB proxy;
- сохранить отдельную cached сборку Hermes operator/router;
- уменьшить polling interval required Docker contract с 15 до 5 секунд;
- добавить regression contracts для cache/tag deduplication и polling interval.

### Планируемый контракт

- production compose-файлы и runtime image names не меняются;
- все существующие Hermes service tags по-прежнему указывают на image, построенный из того же Dockerfile и context;
- `build` остаётся fail-closed агрегатором Docker workflow;
- `docker-build-contract` остаётся required check и продолжает проверять exact PR head;
- CodeQL, supply-chain, static-security, image-security, tests и type-check не ослабляются.

### Риски и ограничения

- ошибка в явном наборе tags могла бы оставить один из Hermes service images непроверенным;
- GHA cache не должен становиться обязательным условием успеха, поэтому cache export остаётся `ignore-error=true`;
- изменение polling не должно менять timeout или fail-closed conclusion handling.

### Миграции и совместимость

- database/runtime migration не требуется;
- production deployment и compose semantics не меняются;
- branch protection contexts не переименовываются.

### Критерии готовности

- workflow contract tests проходят;
- YAML workflow синтаксически валиден;
- protected CI зелёный на exact PR head;
- Docker build check сохраняет имя `build`, а required wrapper сохраняет имя `docker-build-contract`;
- PR merge выполняется только на проверенном head.

## После завершения

### Фактически сделано

- Hermes coder image deduplicated до одной Buildx сборки с четырьмя существующими tags;
- Hermes DB proxy deduplicated до одной Buildx сборки с двумя существующими tags;
- добавлены GHA cache scopes `velvet-hermes-coder` и `velvet-hermes-db-proxy`;
- runtime env preparation удалена из Hermes build-job, но сохранена в Docker Compose validation;
- polling `docker-build-contract` сокращён с 15 до 5 секунд без изменения 40-minute deadline и fail-closed semantics.

### Проверки

- локальные text-contract tests и YAML parse подготовлены до публикации;
- protected GitHub Actions должны подтвердить exact PR head перед merge.

### PR и commit

- ветка: `perf/hermes-ci-cache`;
- базовый commit: `42bd97eedd0807befb92cfcd56cd231e9cc51567`;
- PR/head/merge commit фиксируются GitHub после публикации и зелёного CI.

### Незавершённое

- получить protected CI evidence на опубликованном PR head;
- при движении `main` синхронизировать ветку и повторить exact-head validation.

### Следующий шаг

Опубликовать изменения, открыть PR, проверить реальные Docker/branch-protection jobs и выполнить merge только при полном зелёном required CI.
