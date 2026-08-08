# VL benchmark path contract

- Дата: 2026-08-08
- ID: `2026-08-08-vl-benchmark-path-contract`
- Линия/фаза: Velvet AI / VL, Phase 0 runbook reconciliation
- Статус: `частично`
- Ветка: `docs/vl-benchmark-path-contract`
- Базовый commit: `8ed29fb1917a90b8eede8384acdf181411e3ae53`

Связано: #630, #733, #732.

## Перед началом

### Цель

Устранить operational drift между merged production benchmark workflow и `LOCAL_VISION_RUNBOOK`: workflow принимает evaluation image только из `<VELVET_DATA_DIR>/runtime/vision-benchmark/<basename>`, а runbook после #732 всё ещё показывал плоский файл `runtime/vision-benchmark.jpg`.

### Планируемый объём

- привести runbook к закрытому benchmark directory, который уже enforce-ит workflow;
- зафиксировать первый manual smoke inputs `BENCHMARK / 512 / 1 / cold_unload=false`;
- сохранить прямой host harness как fallback procedure;
- добавить regression contract, чтобы runbook и workflow снова не разошлись;
- не менять workflow execution, model/runtime, flags или queue.

### Критерии готовности

- runbook создаёт `runtime/vision-benchmark/` и помещает image внутрь;
- flat `runtime/vision-benchmark.jpg` больше не фигурирует;
- manual workflow и direct-host examples используют один closed-set path;
- regression test фиксирует directory и first-smoke inputs;
- required CI зелёный на exact head.

## После завершения

### Фактически сделано

- runbook теперь создаёт закрытый каталог `/srv/velvet/data/runtime/vision-benchmark` и пример `smoke-neutral.jpg`;
- раздел запуска разделён на preferred manual production workflow и direct host harness;
- первый smoke зафиксирован как `confirmation=BENCHMARK`, exact deployed source SHA, `output_cap=512`, `rounds=1`, `cold_unload=false`;
- direct harness использует тот же `runtime/vision-benchmark/smoke-neutral.jpg`;
- `tests/test_production_vl_benchmark_workflow.py` теперь проверяет path/input consistency между workflow и runbook.

### Миграции и совместимость

Нет DB/runtime/config migrations. Production workflow, flags, model volume и queues не меняются.

### Незавершённое

- получить required green CI;
- слить только exact green head при `behind_by=0`;
- live benchmark всё ещё требует exact production deployment и закрытый image file на VPS.
