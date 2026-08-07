# Сессия: Hermes coder executable mode preservation hotfix

- Дата: `2026-08-07`
- ID: `hermes-coder-preserve-exec-modes-20260807`
- Линия/фаза: `Hermes / coder reconcile / production hotfix`
- Статус: `частично`
- Ветка: `hotfix/hermes-coders-preserve-exec-modes-20260807`
- Базовый commit: `d9d2688c26e68e52cd841a35275540553a4367e4`

## Перед началом

### Цель

Не позволять `hermes-coders.service` изменять tracked executable modes production checkout во время canonical `reconcile coders`.

### Исходный контекст

Production diagnostics подтвердил четыре mode-only dirty paths в `/srv/velvet`: `codex_context_launcher_runner.py`, `codex_launcher_runner.py`, `sandbox_launcher_client.py`, `sandbox_preflight.py`. Bounded repair PR #693 доказал, что содержимое каждого файла совпадало с `HEAD`, tracked mode был `100755`, worktree mode `0644`, после возврата `0755` checkout стал clean.

Дальнейшая проверка current `main` показала, что `deploy/hermes-reconcile/host_reconcile.py` запускает `deploy/hermes-coders/install.sh` прямо из production checkout. Installer переключает `current-hermes-coders` на `REPO_ROOT`, а current systemd unit перед start/reload выполняет общий `chmod 0644`, в который ошибочно включены эти четыре tracked executable-файла. Поэтому canonical `reconcile coders` мог повторно создать `dirty=true` собственным startup lifecycle и затем провалить финальную checkout verification.

### Планируемый объём

- разделить systemd runtime permission normalization по canonical tracked modes;
- оставить `0644` только для non-executable runtime files;
- применять `0755` к четырём tracked executable launcher/sandbox scripts;
- сделать одинаковое поведение для `ExecStartPre` и `ExecReload`;
- добавить regression contract, запрещающий попадание этих executable paths в `chmod 0644`;
- не менять routing, model policy, secrets, compose topology или reconcile authorization.

### Критерии готовности

- protected CI зелёный;
- четыре executable paths отсутствуют во всех unit `chmod 0644` строках;
- четыре executable paths присутствуют в start/reload `chmod 0755` строках;
- canonical `reconcile coders` после rollout не создаёт mode-only dirty checkout;
- final reconcile checkout verification может завершиться clean на неизменном head.

### Риски и ограничения

Hotfix исправляет только подтверждённый mode drift. Он не гарантирует прохождение provider/runtime smoke и не считается восстановлением coder end-to-end до terminal `reconcile completed`, успешного `coderctl health all` и typed canary.

## После завершения

### Фактически сделано

- `deploy/systemd/hermes-coders.service` разделяет canonical `0644` и `0755` runtime modes;
- `tests/test_hermes_coders_contract.py` фиксирует mode contract для четырёх executable scripts.

### Миграции и совместимость

Миграций данных нет. Unit lifecycle сохраняет прежние команды и порядок, меняется только permission normalization четырёх уже executable tracked файлов.

### Проверки

Требуются protected PR checks. После merge требуется owner-authorized production `opsctl velvet update`, затем `reconcile coders`, terminal reconcile verification, `coderctl health all` и typed read-only canary.

### PR и commit

PR открывается после проверки полного diff относительно current `main`; merge только exact reviewed head после terminal green protected CI.

### Следующий шаг

После merge обновить production до exact merge SHA, подтвердить clean checkout, выполнить canonical `reconcile coders` и завершить end-to-end health/canary.

### Незавершённое

- проверить branch diff;
- открыть PR;
- дождаться protected CI;
- merge в `main`;
- выполнить production update;
- выполнить и дождаться terminal `reconcile coders`;
- подтвердить health router/coders и typed read-only canary.
