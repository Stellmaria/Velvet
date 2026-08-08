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

### Исходный контекст

PR #732 добавил benchmark harness и первоначальный runbook, а PR #733 добавил manual production workflow. Workflow намеренно ограничивает source image отдельным closed-set directory и принимает только basename, чтобы input нельзя было вывести произвольным path из production filesystem. После merge #733 обнаружилось, что пример runbook всё ещё использует прежний flat filename и поэтому первая operator попытка по документации fail-closed не совпадёт с workflow contract.

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

### Риски и ограничения

- этот slice не создаёт evaluation image на VPS и не выполняет benchmark;
- hard-coded `/srv/velvet/data` остаётся только примером для default `VELVET_DATA_DIR`; workflow фактически читает значение из `.env.server`;
- direct host procedure остаётся operator fallback и не ослабляет workflow path validation;
- никаких model pulls, container restarts, queue mutations или AI gate changes нет.

## После завершения

### Фактически сделано

- runbook теперь создаёт закрытый каталог `/srv/velvet/data/runtime/vision-benchmark` и пример `smoke-neutral.jpg`;
- раздел запуска разделён на preferred manual production workflow и direct host harness;
- первый smoke зафиксирован как `confirmation=BENCHMARK`, exact deployed source SHA, `output_cap=512`, `rounds=1`, `cold_unload=false`;
- direct harness использует тот же `runtime/vision-benchmark/smoke-neutral.jpg`;
- `tests/test_production_vl_benchmark_workflow.py` теперь проверяет path/input consistency между workflow и runbook.

### Миграции и совместимость

Нет DB/runtime/config migrations. Production workflow, flags, model volume и queues не меняются.

### Проверки

Первый CI на head `ef890f8ff4cd15b257beec7337a3e82bdc138781` подтвердил type check и branch-protection contract, но project notes contract корректно отклонил неполный worklog: отсутствовали обязательные разделы `Исходный контекст`, `Риски и ограничения`, `Проверки`, `PR и commit`, `Следующий шаг`. Этот commit добавляет только требуемую project-memory структуру; итоговый required CI должен пройти заново на новом exact head.

### PR и commit

- PR: #734 `Align VL benchmark runbook path with production workflow`;
- branch: `docs/vl-benchmark-path-contract`;
- initial failing head: `ef890f8ff4cd15b257beec7337a3e82bdc138781`;
- final tested head и merge SHA фиксируются после required green CI.

### Незавершённое

- получить required green CI;
- слить только exact green head при `behind_by=0`;
- live benchmark всё ещё требует exact production deployment и закрытый image file на VPS.

### Следующий шаг

После merge этого reconciliation slice не добавлять новые code changes до live Phase 0 evidence. Operational next step остаётся: deploy exact merged main, положить closed-set `smoke-neutral.jpg` в `<VELVET_DATA_DIR>/runtime/vision-benchmark/`, затем выполнить manual first smoke `512 / 1 / no cold unload` через production workflow.
