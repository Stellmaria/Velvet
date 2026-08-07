# Сессия: Kael coderctl review_gate runtime dependency hotfix

- Дата: `2026-08-07`
- ID: `kael-coderctl-review-gate-hotfix-20260807`
- Линия/фаза: `Hermes / Kael / production hotfix`
- Статус: `частично`
- Ветка: `hotfix/kael-review-gate-runtime`
- Базовый commit: `bcaa33df46072881b3a87c8a02628dc53f239e4b`

## Перед началом

### Цель

Восстановить canonical coder control Каэля, который в production падает до health/router запроса с `ModuleNotFoundError: No module named 'review_gate'`.

### Исходный контекст

Live acceptance Каэля подтвердил корректное fail-closed поведение `coder_delegate`, но `python /opt/data/tools/coderctl.py health all` завершился на Python import до обращения к central coder router. Production Velvet при этом healthy, checkout clean и находится на базовом commit.

`deploy/hermes-operator/coderctl.py` добавляет собственный каталог в `sys.path` и импортирует соседний `review_gate.py`. `deploy/hermes-entities/reconcile.sh` до hotfix устанавливал в runtime `/opt/data/tools/` только `coderctl.py` и `runctl.py`, поэтому обязательная runtime-зависимость `review_gate.py` отсутствовала.

### Планируемый объём

- сделать `review_gate.py` обязательным source-файлом entities reconcile;
- устанавливать его рядом с `coderctl.py` в `/opt/data/tools/`;
- добавить regression contract на source/runtime paths;
- не менять routing, privileges, model policy, ledger schema или production data.

### Критерии готовности

- reconcile fail-closed при отсутствии source `review_gate.py`;
- `review_gate.py` устанавливается рядом с `coderctl.py` owner-only mode `0500`;
- regression test фиксирует обе стороны deployment contract;
- focused tests, Bash syntax и protected CI проходят;
- после merge и owner-authorized rollout `coderctl.py health all` доходит до central router вместо падения на Python import.

### Риски и ограничения

Hotfix устраняет первый подтверждённый blocker control-plane, но сам по себе не доказывает здоровье coder router или coder containers. Production update/reconcile и live canary являются отдельной стадией.

## После завершения

### Фактически сделано

- `review_gate.py` добавлен в required source contract `deploy/hermes-entities/reconcile.sh`;
- dependency устанавливается рядом с `coderctl.py` в `$hermes_data/tools/review_gate.py` mode `0500`;
- `tests/test_hermes_entities_contract.py` фиксирует source и runtime target dependency.

### Миграции и совместимость

SQL-миграций нет. API/router/ledger contracts не меняются. Изменение только дополняет runtime package Каэля уже существующим модулем из того же operator source tree.

### Проверки

Требуются protected CI checks PR и последующий live `coderctl.py health all` после rollout.

### PR и commit

PR создаётся после публикации ветки. Финальный head фиксируется GitHub после добавления этой worklog записи.

### Незавершённое

- открыть PR и дождаться terminal protected CI;
- merge только exact reviewed head;
- выполнить production update и `reconcile entities`;
- повторить `coderctl.py health all` и Kael `coder_delegate` canary.

### Следующий шаг

Открыть PR из `hotfix/kael-review-gate-runtime` в `main`, дождаться зелёных protected checks и затем выполнить owner-authorized merge и production rollout.
