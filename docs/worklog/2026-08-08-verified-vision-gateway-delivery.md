# Verified vision-gateway delivery

- Дата: 2026-08-08
- ID: `2026-08-08-verified-vision-gateway-delivery`
- Линия/фаза: VL / production delivery hardening
- Статус: `частично`
- Ветка: `feat/verified-vision-gateway-delivery`
- Базовый commit: `efbb5d89dd429b9ce03c486fb5724303f1109614`

## Перед началом

### Цель

Дать отдельному `vision-gateway` проверяемый immutable build/deploy path, чтобы изменения gateway-кода из canonical VL линии нельзя было ошибочно считать развернутыми только потому, что основной application image и checkout уже обновлены.

### Исходный контекст

После merge #738 canonical `LOCAL_MAIN=qwen3.5:9b` получил no-reasoning structured-output contract и fail-closed benchmark semantics. Однако существующий `publish-image.yml` собирал только основной `ghcr.io/stellmaria/velvet` image и не реагировал на `vision_gateway/**`, а обычный production deploy не обновлял отдельный `vision-gateway` service. В результате новый source commit мог сосуществовать со старым gateway image, а benchmark не проверял revision работающего gateway.

### Планируемый объём

- отдельный verified GHCR image `ghcr.io/stellmaria/velvet-vision-gateway`;
- push trigger на `vision_gateway/**`, `Dockerfile.vision-gateway`, gateway requirements и сам publish workflow;
- revision/source/component OCI labels, Trivy blocking scan, CycloneDX SBOM и immutable digest metadata;
- отдельный manual production workflow с `DEPLOY_VISION_GATEWAY`, exact current-main source commit и immutable gateway digest;
- gateway-only deploy без рестарта bot или `vision-runtime`;
- deploy из clean `git archive` snapshot exact source commit, без reset/checkout активного production tree;
- atomic persist `VISION_GATEWAY_IMAGE` в `.env.server`;
- rollback на сохраненный предыдущий gateway image ID при health/provenance failure;
- post-deploy assertions, что bot и `vision-runtime` container IDs не изменились;
- production VL benchmark gate на immutable gateway image, exact revision и component label.

### Критерии готовности

- gateway publish workflow не собирает основной bot image;
- опубликованный gateway image имеет exact source revision и component label;
- deploy workflow manual-only, serialized через `velvet-production` и принимает только canonical gateway digest namespace;
- production deploy заменяет только `vision-gateway` и сохраняет предыдущий image для rollback;
- успешный deploy проверяет health, running image ID, exact revision и неизменность bot/runtime container IDs;
- benchmark не запускается на local/неверифицированном gateway image или revision, отличном от `source_commit`;
- shell script проходит `bash -n`, workflow contracts покрыты тестами;
- required GitHub CI зеленый на exact PR head;
- merge только при `behind_by=0`.

### Риски и ограничения

- этот PR не выполняет production deploy и не доказывает runtime-поведение нового gateway image;
- активный production checkout не сбрасывается и не очищается этим deploy path;
- gateway recreation может кратко прервать новый входящий VL request, поэтому фактический rollout остается отдельной контролируемой операцией;
- shared CPU arbitration между Storage Librarian и VL остается отдельным follow-up;
- model route, model digest, queue/backfill и optional cloud/uncensored routes не меняются.

## После завершения

### Фактически сделано

На ветке добавлены отдельные publish/deploy workflows для `vision-gateway`, rollback-safe gateway-only deploy script, persisted immutable gateway pin, exact revision/component verification и новый provenance gate production VL benchmark. Добавлены contract tests, включая `bash -n` deploy script и проверки неизменности bot/runtime semantics.

### Миграции и совместимость

Миграций БД нет. Новый `VISION_GATEWAY_IMAGE` записывается в существующий `.env.server` только во время отдельного manual gateway deploy. До такого deploy текущая production конфигурация не меняется.

### Проверки

Локально подготовлены contract assertions для publish/deploy/benchmark workflows и `bash -n` deploy script. Полный required GitHub CI будет источником истины перед merge.

### PR и commit

PR будет создан после фиксации полного diff. Merge commit отсутствует до прохождения required CI.

### Незавершённое

Не выполнялись publish нового gateway image, production gateway deploy и повторный isolated `512 / 1 / no-cold` benchmark. Эти действия требуют уже merged delivery contract и immutable publish evidence.

### Следующий шаг

После green merge дождаться автоматического publish exact-main gateway image, получить immutable digest artifact, выполнить отдельный `DEPLOY_VISION_GATEWAY` rollout, проверить provenance/health и затем повторить один isolated canonical `512 / 1 / no-cold` smoke до любых 384/768 или batch шагов.
