# VL LOCAL_MAIN benchmark and identity pin

- Дата: 2026-08-08
- ID: `2026-08-08-vl-local-main-benchmark-pin`
- Линия/фаза: Velvet AI / VL, Phase 0 benchmark readiness
- Статус: `частично`
- Ветка: `feat/vl-local-main-benchmark-pin`
- Базовый commit: `4099d7f8e449564e84e74e71d0633549c0e42c3a`

Связано: #630, #727, #709, #712, #718.

## Перед началом

### Цель

Устранить configuration drift между текущим canonical #630 и server templates и сделать существующий local-VL benchmark воспроизводимым на реальном VPS без открытия gateway наружу и без выдачи bot-контейнеру Docker socket.

### Исходный контекст

После merge #727 application router соответствует 3-role policy #630, но deployment/documentation surface сохранял старый #505 default `qwen3-vl:8b-instruct-q4_K_M` и пустой model digest. Production evidence при этом уже фиксировал `qwen3.5:9b`, digest prefix `6488c96fa5fa`.

Существующий `scripts/benchmark_vision_gateway.py` измерял cold latency, warm median/max и строковые Docker stats. Для benchmark scorecard #630 не хватало warm p50/p95, schema validity, failure rate, numeric resource peaks, swap, output-cap evidence и runtime image identity.

### Планируемый объём

- закрепить current `LOCAL_MAIN=qwen3.5:9b` и digest prefix `6488c96fa5fa` в server/local env examples и Compose fallbacks;
- сохранить `AI_QUALITY_ENABLED=false`, `CLOUD_PRO=false`, `LOCAL_UNCENSORED=false`;
- расширить существующий benchmark harness вместо создания второго инструмента;
- добавить host-side transport через `docker exec` в bot для internal-only gateway;
- собрать cold/warm p50/p95, schema validity, failure rate, resource peaks, swap и runtime image identity;
- добавить output cap как явный benchmark parameter;
- обновить canonical VL docs/runbook с #505 на #630;
- добавить regression contracts на harness и model/digest pin;
- не выполнять production model pull, batch enqueue или feature enable этим PR.

### Критерии готовности

- active server templates и Compose fallback не содержат старый 8B default;
- gateway/loader получают одинаковый `qwen3.5:9b` + `6488c96fa5fa` pin;
- benchmark может работать на host через internal gateway без публикации порта;
- benchmark output содержит automated scorecard fields из #630 и отдельные manual quality fields;
- output caps 384/512/768 можно прогонять одним и тем же harness/evaluation image;
- regression tests и required CI зелёные на финальном head;
- merge выполняется только при `behind_by=0`.

### Риски и ограничения

- digest `6488c96fa5fa` закреплён как подтверждённый production prefix, а не как полный digest; это соответствует уже существующему prefix-match contract loader/gateway;
- runtime image, собранный локально, может не иметь registry `RepoDigests`; harness сохраняет immutable image ID, а registry digest остаётся обязательным после публикации image;
- `tokens_per_second_estimate` использует completion tokens / total request latency и не объявляется чистой decoder-only скоростью;
- benchmark script не выполняет semantic/quality inference через archive queues;
- live VPS benchmark остаётся deployment acceptance после merge и не подменяется CI;
- timeout 300 секунд этим slice не увеличивается.

### Стабилизационный допуск

1. Меняется существующий VL benchmark/deployment contract, новая продуктовая функция не добавляется.
2. Production feature gates остаются fail-closed.
3. Public network surface не расширяется.
4. Model identity становится строже, а не слабее.
5. Automatic mass backfill не появляется.

## После завершения

### Фактически сделано

- `.env.server.example` и `.env.vision-local.example` переведены на `qwen3.5:9b` с `VISION_MODEL_EXPECTED_DIGEST=6488c96fa5fa`;
- `docker-compose.server.yml` использует тот же model/digest как fallback для loader/runtime/gateway;
- optional `CLOUD_PRO` и `LOCAL_UNCENSORED`, global `AI_QUALITY_ENABLED` остаются false;
- benchmark contract поднят до version 2;
- добавлены explicit `--max-output-tokens`, `--expected-digest`, `--cold-unload`, warm p50/p95, schema validity, success/failure rate, numeric CPU/RAM/swap peaks и runtime image identity;
- host benchmark может делать HTTP через `--request-container`/`docker exec`, одновременно сохраняя host-level Docker resource evidence;
- добавлены manual scorecard placeholders для omissions/hallucinations/visual quality/OCR/pose/composition/owner score;
- `docs/AI_VISION.md` и `docs/LOCAL_VISION_RUNBOOK.md` переведены на canonical #630 и controlled rollout policy;
- добавлены `tests/test_benchmark_vision_gateway.py` и `tests/test_vl_local_main_pin_contract.py`.

### Миграции и совместимость

DB migration нет. Существующие model volume, quality rows и owner plans не изменяются. Application route compatibility names `FLASH/PRO/SENSITIVE` не переименовываются. Изменяется только canonical default identity для local server/bootstrap surfaces и benchmark/reporting contract.

### Проверки

- локальная pure-Python проверка benchmark helper contract: 5 tests passed до публикации ветки;
- GitHub required CI должен подтвердить итоговый branch head;
- live production benchmark не считается выполненным этим code PR.

### PR и commit

- branch: `feat/vl-local-main-benchmark-pin`;
- PR будет создан после завершения bounded code/doc/test slice;
- exact tested head и merge SHA фиксируются после required green CI.

### Незавершённое

- получить required green CI и исправить только фактические regressions;
- синхронизировать branch с актуальным `main`, если параллельный PR #731 успеет войти;
- слить только exact green head при `behind_by=0`;
- после merge выполнить single-image VPS benchmark caps 384/512/768 и заполнить manual scorecard;
- не включать controlled batches до сохранённого single-image evidence.

### Следующий шаг

После merge выполнить live Phase 0 benchmark на production VPS для pinned LOCAL_MAIN, выбрать output cap по latency/schema/quality evidence и только затем рассматривать controlled batch 10.
