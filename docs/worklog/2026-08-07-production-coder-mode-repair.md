# Сессия: bounded production coder mode repair

- Дата: `2026-08-07`
- ID: `production-coder-mode-repair-20260807`
- Линия/фаза: `Hermes / production repair`
- Статус: `частично`
- Ветка: `ops/repair-production-coder-modes-20260807`
- Базовый commit: `0273e46cded65b12575956b1a4dc3f5cd2856305`

## Перед началом

### Цель

Без сброса содержимого production checkout восстановить четыре tracked executable-файла Hermes coder source tree, которые блокируют canonical `reconcile coders` состоянием `dirty=true`.

### Исходный контекст

Production diagnostics run после PR #691 подтвердил checkout `/srv/velvet` на commit `0dceb104a8d5c6a1a25dda07c708b916f2e9439f` с ровно четырьмя modified paths:

- `deploy/hermes-coders/codex_context_launcher_runner.py`;
- `deploy/hermes-coders/codex_launcher_runner.py`;
- `deploy/hermes-coders/sandbox_launcher_client.py`;
- `deploy/hermes-coders/sandbox_preflight.py`.

В Git эти четыре файла tracked как executable `100755`. До ремонта нельзя считать, что изменения только mode-only, поэтому production repair обязан подтвердить совпадение blob SHA для HEAD и worktree и точный worktree mode `0644` перед любой mutation.

### Планируемый объём

- добавить одноразово push-triggered production repair workflow;
- требовать exact production HEAD `0dceb104a8d5c6a1a25dda07c708b916f2e9439f`;
- требовать ровно четыре ожидаемые строки `git status` и никаких других dirty paths;
- для каждого файла подтвердить tracked mode `100755`, worktree mode `0644` и идентичный blob SHA;
- только после всех проверок выполнить `chmod 0755` на этих четырёх exact paths;
- подтвердить полностью clean checkout;
- не выполнять reset, checkout, clean, update, restart или reconcile в repair workflow.

### Критерии готовности

- protected CI PR зелёный;
- merge-triggered repair run завершается `success`;
- все четыре файла доказаны content-identical относительно HEAD до mutation;
- production checkout после ремонта `clean`;
- после этого Kael может отдельно выполнить owner-authorized canonical update и `reconcile coders`.

### Риски и ограничения

Workflow намеренно fail-closed. Любой дополнительный dirty path, содержательный diff, неожиданный mode или другой production HEAD блокирует mutation. Ремонт не утверждает, что Hermes coder runtime уже здоров, и не заменяет последующий canonical reconcile.

## После завершения

### Фактически сделано

- добавлен bounded repair workflow `.github/workflows/repair-production-coder-checkout-modes.yml`;
- repair ограничен четырьмя ранее диагностированными paths;
- перед `chmod` проверяются exact dirty set, tracked/worktree modes и equality blob SHA;
- postcondition требует полностью clean checkout.

### Миграции и совместимость

SQL/data migrations отсутствуют. Application API, routing, model policy и Hermes ledger contracts не меняются. Production mutation ограничена восстановлением executable mode четырёх tracked файлов при доказанно неизменном содержимом.

### Проверки

Требуются protected PR checks и merge-triggered production repair run. После production repair отдельно требуется `opsctl velvet update`, затем `reconcile coders`, `coderctl health all` и typed read-only canary.

### PR и commit

PR создаётся после проверки полного branch diff. Merge допускается только на exact reviewed head после terminal green protected CI.

### Следующий шаг

После успешного production repair подтвердить `dirty=false`, обновить Velvet production checkout до текущего merged `main`, затем выполнить owner-authorized `reconcile coders` и end-to-end Kael coder canary.

### Незавершённое

- дождаться terminal green protected CI на PR;
- слить exact reviewed head в `main`;
- получить merge-triggered production repair evidence;
- подтвердить `working_tree_after=clean`;
- через Kael выполнить canonical production update и `reconcile coders`;
- завершить `coderctl health all` и typed read-only canary.
