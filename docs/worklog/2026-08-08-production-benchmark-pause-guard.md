# Production VL benchmark pause guard

- Дата: 2026-08-08
- ID: `2026-08-08-production-benchmark-pause-guard`
- Линия/фаза: VL / production benchmark hardening
- Статус: `завершено`
- Ветка: `fix/production-benchmark-pause-guard`
- Базовый commit: `c89ec65458c5143a4e4708b3afbbd7099c4e8abc`

## Перед началом

### Цель

Закрыть operational defect, при котором ручная изоляция production VL benchmark через `docker pause` основного bot-контейнера оставляла `State.Running=true`, но блокировала exec-based healthcheck и переводила контейнер в `unhealthy`.

### Исходный контекст

Диагностика production показала, что приложение и PostgreSQL не были первичной причиной инцидента. Bot и Arthur были намеренно поставлены на Docker pause ручным benchmark wrapper для освобождения ресурсов. Hermes корректно увидел unhealthy, потому что healthcheck не мог выполняться внутри paused container. Канонический workflow проверял только `State.Running`, чего недостаточно для такого состояния.

### Планируемый объём

- добавить fail-closed проверку running/paused/health для `bot`, `vision-runtime` и `vision-gateway` до benchmark;
- повторно проверить container IDs и Docker state после benchmark;
- сохранить существующую immutable gateway provenance validation;
- запретить runtime mutation commands в regression contract workflow;
- закрепить в Local Vision runbook запрет на pause/stop/kill production services ради benchmark isolation.

### Критерии готовности

- canonical production benchmark отказывается работать с paused или unhealthy container;
- benchmark подтверждает, что containers не были заменены и остались healthy/unpaused после run;
- workflow не содержит pause/unpause/stop/kill mutations;
- runbook явно направляет оператора к idle/deferred или documented Librarian lifecycle вместо pause production services;
- required CI проходит перед merge.

### Риски и ограничения

Изменение не может технически запретить владельцу VPS вручную выполнить произвольный `docker pause` вне репозитория. Оно делает такой state fail-closed для canonical workflow и закрепляет безопасный operational contract. Benchmark по-прежнему требует `STORAGE_LIBRARIAN_AUTO_ENQUEUE=false`; управление Librarian lifecycle остаётся отдельной explicit production operation.

## После завершения

### Фактически сделано

Production benchmark workflow получил общий `assert_container_ready`: он требует `State.Running=true`, `State.Paused=false` и `health=healthy`, если healthcheck объявлен. Проверка выполняется для bot, vision runtime и gateway до benchmark и повторно после него. После run также сравниваются исходные и текущие container IDs. Exit code benchmark сохраняется и возвращается только после post-run state validation.

Regression test запрещает `docker pause`, `docker unpause`, `docker stop` и `docker kill` в production benchmark workflow. Local Vision runbook теперь прямо запрещает использовать pause/unpause wrapper для изоляции local inference workload.

### Миграции и совместимость

SQL-миграций, изменений `.env.server`, Docker image format или persistent data нет. Existing verified vision gateway provenance gate сохранён. Production deployment не выполняется этим PR.

### Проверки

Добавлен regression coverage в `tests/test_production_vl_benchmark_workflow.py`. Required GitHub Actions должны подтвердить tests, type check, security supply chain, branch protection и project notes contract.

### PR и commit

PR создаётся в `main` из `fix/production-benchmark-pause-guard`. Ветка была перенесена на актуальный `main` после появления параллельного PR #739, чтобы сохранить его verified gateway changes без merge-конфликта.

### Незавершённое

После merge отдельный production deploy или benchmark запускается только при необходимости. Этот PR не меняет текущий runtime state VPS и не отключает уже включённый Storage Librarian backfill.

### Следующий шаг

Дождаться полного зелёного required CI, проверить актуальность head относительно `main` и выполнить authorized merge PR.
