# Сессия: Hermes release root runner

- Дата: `2026-08-06`
- ID: `hermes-release-root-runner-20260806`
- Линия/фаза: `server operations / Hermes coder deployment automation`
- Статус: `частично`
- Ветка: `fix/hermes-release-root-runner`
- Базовый commit: `7490abd4c44bb53931b679340625bfc3ac7949cc`
- Связанные PR и release evidence: `#648`, `#649`, `#651`, `#653`, `#654`, release `7490abd4c44bb53931b679340625bfc3ac7949cc`

## Перед началом

### Цель

Заменить неработающий `sudo -n env ... release.sh` на узкую root-owned
deployment boundary и перенести release lock из общего `/tmp` в root-owned
каталог `/run/lock/hermes-coders`.

### Исходный контекст

Canonical production release `7490abd4c44bb53931b679340625bfc3ac7949cc`
успешно активирован вручную:

- `hermes-coders.service` работает `active/exited/success`;
- launcher socket и service активны;
- Velvet и Max coder containers работают healthy с нулевыми restart count;
- immutable image IDs, exact release mounts и AppArmor profile подтверждены;
- compatibility override не использовался;
- временный `compose.codex-runner-hotfix.yaml` архивирован.

GitHub Actions deploy workflow при каждом запуске успешно подтверждал exact
current main и создавал detached worktree, но затем закономерно завершался на
`sudo: a password is required`. Разрешать `NOPASSWD` для versioned script из
worktree, которым владеет deployment user, нельзя: локальная подмена файла
дала бы произвольное root execution.

Отдельно release lock создавался как
`${TMPDIR:-/tmp}/velvet-hermes-coder-release.lock`. На Ubuntu с
`fs.protected_regular=2` ранее существовавший user-owned файл в `/tmp`
блокировал root release до ручного восстановления ownership.

### Планируемый объём

- добавить root-owned release runner с фиксированными production paths;
- независимо fetch-ить current `main` из hardcoded GitHub repository;
- создавать exact detached worktree из root-owned bare mirror;
- отказываться от non-root-owned, dirty или несовпадающего release tree;
- запускать versioned release script с очищенным environment;
- задавать `TMPDIR=/run/lock/hermes-coders`;
- добавить root-only installer для runner и точечного sudoers command;
- перевести workflow на `sudo -n /usr/local/sbin/hermes-coders-release <SHA>`;
- добавить regression contracts против `NOPASSWD: ALL`, `SETENV` и
  user-owned release execution.

### Критерии готовности

- workflow не создаёт и не исполняет deployment-user-owned worktree;
- root runner повторно проверяет exact current `main`;
- release mirror и release tree принадлежат root;
- lock создаётся под `/run/lock/hermes-coders`;
- sudoers разрешает только root-owned runner;
- required protected-branch CI зелёный;
- после one-time bootstrap fresh release workflow завершается успешно.

## После завершения

### Фактически сделано

- добавлен root release runner с hardcoded repository URL и production paths;
- runner использует отдельный root-owned bare mirror и exact detached worktree;
- existing worktree принимается только при exact SHA, root ownership и clean state;
- release script запускается через очищенный `env -i`;
- lock namespace перенесён в `/run/lock/hermes-coders` через bounded `TMPDIR`;
- добавлен root-only installer с `visudo` validation и mode `0440`;
- workflow вызывает только `/usr/local/sbin/hermes-coders-release <SHA>`;
- добавлены deployment security regression contracts.

### Риски и ограничения

- runner и sudoers требуют однократной ручной bootstrap-установки после merge;
- runner намеренно закреплён на `/srv/velvet`, `/srv/hermes-coders` и user `velvet`;
- GitHub repository URL hardcoded, чтобы production remote config не расширял trust;
- root mirror требует исходящий HTTPS access к GitHub;
- старые deployment-user-owned release worktrees не принимаются runner-ом.

### Миграции и совместимость

Миграций базы, volumes, auth, secrets, ledger или workspaces нет. Текущий
production runtime не изменяется этим PR. Новый runner влияет только на
будущие exact-current-main releases.

### Проверки

- `bash -n` для runner, installer и workflow shell fragments;
- regression contracts для root ownership, exact-main fetch и clean worktree;
- отрицательные assertions против `sudo -n env`, `NOPASSWD: ALL`, `SETENV`,
  user-owned worktree execution и `/tmp` lock namespace;
- существующие Hermes release, rollback, AppArmor и runtime contracts;
- полный protected-branch required CI.

### PR и commit

- PR создаётся из `fix/hermes-release-root-runner`;
- base: `7490abd4c44bb53931b679340625bfc3ac7949cc`;
- итоговый head и merge commit фиксируются после required CI.

### Незавершённое

- открыть draft PR;
- дождаться полного required CI;
- выполнить squash merge без обхода branch protection;
- создать fresh exact-current-main release branch;
- однократно установить root runner и sudoers из merged exact release;
- подтвердить успешный non-interactive workflow release.

### Следующий шаг

Проверить локальные shell/Python contracts, открыть draft PR и дождаться
required CI.
