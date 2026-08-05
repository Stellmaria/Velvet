# Сессия: Hermes coder release runtime import graph

- Дата: `2026-08-05`
- ID: `hermes-runtime-release-import-graph-20260805`
- Линия/фаза: `server operations / Hermes coder production release`
- Статус: `частично`
- Ветка: `fix/hermes-coder-runtime-release-graph`
- Базовый commit: `81cab6e0c0f3cc0cc1fa9a9a0e5338db82e60102`
- Связанные issue, PR и release evidence: `#592`, `#638`, release run `30983346625`

## Перед началом

### Цель

Устранить подтверждённую несовместимость release-bound Python runtime Hermes
coders и сделать так, чтобы плохой import graph отклонялся до пересоздания
production-контейнеров.

### Исходный контекст

Release `74bfb3a19506e5b2a387f4de62b711808ea88a4c` смонтировал текущие wrapper
modules, но не смонтировал release-bound `codex_runner.py`. Контейнеры объединили
новые wrappers со старой image-копией базового runner и упали с:

```text
ImportError: cannot import name 'Handler' from 'codex_runner'
```

Временный read-only mount показал второй дефект: detached worktree был создан
под `umask 077`, поэтому файл имел mode `0600`, а container UID `10000:10000`
получал:

```text
PermissionError: [Errno 13] Permission denied: '/app/codex_runner.py'
```

После canonical-equivalent mount и изменения mode на `0644` оба coder
containers восстановились как `running`, `healthy`, `restarts=0`.

### Планируемый объём

- смонтировать базовые `codex_runner.py` и `codex_routed_runner.py` из exact
  release для обоих coder services;
- добавить их в существующий runtime source permission guard;
- проверять полный локальный Python import graph до `docker compose up`;
- добавить regression coverage для mounts, permissions и imports;
- не менять AppArmor, auth, data, volumes или chat/proxy lifecycle;
- открыть PR и слить только после зелёного required CI.

### Критерии готовности

- оба coder services используют одинаковый полный release-bound module graph;
- container UID может читать все bind-mounted runtime sources;
- несовместимый import graph отклоняется существующим guard до recreation;
- tests, type check, notes, security, Docker и protection contracts зелёные;
- merge выполняется штатно, без обхода branch protection.

### Риски и ограничения

- production продолжает работать на временном read-only override до нового
  exact-main release;
- systemd units остаются остановленными до успешного canonical release;
- host-side import probe проверяет API compatibility исходников, а container
  health и runtime smoke остаются обязательными post-start проверками;
- отдельный rollback lifecycle defect не маскируется этим патчем и требует
  собственного regression scope.

## После завершения

### Фактически сделано

- `codex_runner.py` и `codex_routed_runner.py` добавлены в canonical runtime
  mounts обоих coder services;
- оба файла добавлены в `RUNTIME_SOURCES`, поэтому guard выставляет только
  требуемый world-read bit и затем валидирует его;
- guard запускает изолированный import probe с `PYTHONDONTWRITEBYTECODE=1`;
- probe импортирует весь локальный graph до любого production Compose up;
- добавлены regression tests и production evidence.

### Риски и ограничения

- временный production override удаляется только после успешного нового release;
- systemd reconciliation не запускается до подтверждения healthy canonical
  containers;
- AppArmor policy не ослаблена;
- persistent state не изменяется.

### Миграции и совместимость

- database migrations отсутствуют;
- Docker image rebuild не требуется для release-bound Python modules;
- auth, runs, workspaces, secrets, data и volumes не меняются;
- новый mount заменяет несовместимую image-копию точной release-версией.

### Проверки

Добавлены проверки для:

- двух canonical mounts каждого runtime module;
- покрытия базовых modules runtime source guard;
- успешного repository import graph;
- fail-before-recreation поведения существующего release/systemd guard path.

### PR и commit

- ветка: `fix/hermes-coder-runtime-release-graph`;
- base: `81cab6e0c0f3cc0cc1fa9a9a0e5338db82e60102`;
- PR: `#638`;
- merge commit фиксируется после required CI.

### Незавершённое

- дождаться всех required CI contexts;
- исправить только подтверждённые failures;
- слить PR после зелёного CI;
- выпустить новый exact-current-main Hermes release;
- удалить временный production override после canonical mount verification;
- отдельно исправить quiesce order transactional systemd rollback.

### Следующий шаг

Дождаться required CI для PR `#638`, выполнить штатный squash merge, затем
выпустить exact-current-main release без запуска systemd reconciliation до
подтверждения healthy canonical coder containers.
