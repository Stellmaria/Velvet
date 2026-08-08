# Сессия: параллельный Docker CI

- Дата: 2026-08-08
- ID: 2026-08-08-parallel-docker-ci
- Линия/фаза: CI / ускорение merge gate
- Статус: частично
- Ветка: perf/parallel-docker-ci
- Базовый commit: fa360df542e7dcc44ce2f98eb44580548055ad41

## Перед началом

### Цель

Сократить время ожидания зелёных проверок для Docker-heavy PR без ослабления обязательных проверок и без изменения существующего контекста `build`, который контролирует `docker-build-contract`.

### Исходный контекст

Последние PR обычно проходили merge gate примерно за 2.5–3.5 минуты, а Docker-heavy изменения доходили примерно до 5 минут. В медленном прогоне Velvet, Krita и Hermes Docker surfaces строились последовательно внутри одного job, поэтому критический путь был суммой независимых сборок.

### Планируемый объём

Разделить Docker surfaces на независимые GitHub Actions jobs, сохранить selective surface detection и GHA cache, добавить отдельную валидацию Docker contracts и оставить финальный fail-closed job с именем `build` для совместимости с branch protection contract.

### Критерии готовности

- независимые Velvet, Supervisor, Vision, Krita и Hermes сборки могут выполняться параллельно;
- неизменённые surfaces пропускаются на уровне job;
- финальный check `build` успешен только если selector и validation успешны, а выбранные build jobs не упали;
- существующий `docker-build-contract` продолжает видеть check-run `build`;
- контрактные и обязательные CI проверки PR проходят.

### Риски и ограничения

Разделение на jobs создаёт отдельные GitHub-hosted runners и требует повторного checkout/setup для выбранных surfaces. Krita smoke должен оставаться в том же job, где собран Krita image. Hermes build требует собственного временного окружения compose. Branch protection не меняется в этой задаче.

## После завершения

### Фактически сделано

`docker-build.yml` разделён на selector, validation, пять surface-specific build jobs и финальный aggregator `build`. Тяжёлые image surfaces больше не обязаны ждать друг друга. Добавлены контрактные тесты структуры workflow и fail-closed агрегатора.

### Миграции и совместимость

Миграций данных нет. Required branch protection contexts не менялись. Контекст `build`, который опрашивает `docker-build-contract`, сохранён.

### Проверки

Локально выполнен `python -m unittest -v tests/test_docker_build_workflow_contract.py`: 5 тестов успешно. Также проверены старые строковые контракты selective Docker workflow. GitHub Actions PR #720 запущены; итог обязательных CI проверок ещё ожидается на момент этой записи.

### PR и commit

PR: #720. Основные commits ветки: `a046d4861b2c376a445f9ba150efcb07b007f087`, `ed07d75675392ea7a5833a73f36d990952fb5c59`.

### Незавершённое

Нужно получить зелёные обязательные GitHub checks и после merge измерить фактический выигрыш на Docker-heavy PR. Polling в `docker-build-contract` намеренно не менялся в этой итерации.

### Следующий шаг

После зелёного CI слить PR в `main`; затем сравнивать критический путь новых Docker-heavy прогонов с прежними 5-минутными прогонами.
