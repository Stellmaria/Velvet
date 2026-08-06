# Сессия: Hermes Codex runner Git HTTPS и temp AppArmor

- Дата: `2026-08-06`
- ID: `hermes-codex-runner-git-temp-20260806`
- Линия/фаза: `server operations / Hermes coder canonical production release`
- Статус: `частично`
- Ветка: `fix/hermes-codex-runner-git-temp`
- Базовый commit: `65b48fc9f5e23f5cdd275354bab2ad72fdc76fe6`
- Связанные PR и release evidence: `#648`, `#649`, `#651`, release `6707d60802d888bd5a0b865217a17f8ea13dcc83`

## Перед началом

### Цель

Устранить подтверждённый AppArmor отказ canonical coder runtime smoke без
расширения доступа за пределы Git HTTPS helpers и собственного Codex temp.

### Исходный контекст

Canonical release `6707d60802d888bd5a0b865217a17f8ea13dcc83` успешно прошёл
idle gate, Brain Vault, launcher staging, immutable image pinning и sandbox
preflight. Оба coder container были созданы с `apparmor=hermes-codex-runner`.

`runtime_smoke.py` завершился на `git clone`:

```text
fatal: cannot exec 'remote-https': Permission denied
```

Kernel audit указал точный запрещённый executable:

```text
apparmor="DENIED" operation="exec" profile="hermes-codex-runner"
name="/usr/lib/git-core/git"
```

Отдельный audit показал, что Codex не может выполнить `chmod` в собственном
`/opt/codex/tmp/arg0`, из-за чего login status печатает warning перед smoke.

Rollback вернул предыдущий current link и image IDs; coder и chat containers
после rollback работают `healthy/restarts=0`. Legacy systemd drop-in,
присутствующий после отказа, восстановлен rollback-ом и не является причиной
canonical failure.

### Планируемый объём

- разрешить execute только для Git core executable, необходимых HTTPS transport;
- разрешить write/lock только внутри `/opt/codex/tmp`;
- сохранить read-only contract для остального `/opt/codex`;
- добавить regression contract по exact production audit paths;
- не менять seccomp, capabilities, volumes, auth, ledger, workspaces или secrets;
- слить только после полного зелёного required CI.

### Критерии готовности

- `/usr/lib/git-core/git`, `git-remote-http` и `git-remote-https` имеют `ix`;
- broad `/usr/lib/git-core/** ix` отсутствует;
- `/opt/codex/tmp` writable, остальной `/opt/codex` остаётся read-only;
- regression tests и required CI зелёные;
- production acceptance выполняется fresh exact-current-main release.

## После завершения

### Фактически сделано

- в canonical `hermes-codex-runner` добавлены exact `ix` rules для Git HTTPS
  transport executable;
- `/opt/codex/tmp` получил локальный `rw/rwk` contract;
- общий `/opt/codex/** r` и остальные deny boundaries сохранены;
- добавлен regression test, запрещающий broad Git core execute rule;
- production persistent state этим PR не изменялся.

### Риски и ограничения

- AppArmor profile validation в CI проверяет source contract, а фактический
  kernel reload подтверждается только production release;
- netlink bind и runc signal audit denials не являлись причиной smoke failure и
  намеренно не расширены;
- deploy workflow всё ещё требует интерактивный sudo для root release;
- production unit остаётся failed/disabled/runtime-masked до fresh release.

### Миграции и совместимость

Миграций базы и данных нет. Изменяется только canonical AppArmor source profile.
Runtime user, no-new-privileges, seccomp, read-only root filesystem и Docker
socket denials остаются без изменений.

### Проверки

- exact AppArmor source assertions для Git helper executable;
- exact `/opt/codex/tmp` write contract;
- negative assertion против broad `/usr/lib/git-core/** ix`;
- полный protected-branch required CI после открытия PR.

### PR и commit

- PR создаётся из `fix/hermes-codex-runner-git-temp`;
- base: `65b48fc9f5e23f5cdd275354bab2ad72fdc76fe6`;
- итоговый head и merge commit фиксируются после required CI.

### Незавершённое

- открыть PR и дождаться required CI;
- выполнить squash merge без обхода branch protection;
- создать fresh release branch от нового current main;
- повторить canonical production acceptance;
- подтвердить отсутствие Git/Codex temp AppArmor denials;
- удалить temporary compatibility artifacts только после acceptance.

### Следующий шаг

Открыть draft PR, дождаться полного required CI, выполнить squash merge и
повторить canonical release с exact-current-main SHA.
