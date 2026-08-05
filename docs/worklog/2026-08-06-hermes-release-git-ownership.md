# Сессия: Hermes release Git ownership

- Дата: `2026-08-06`
- ID: `hermes-release-git-ownership-20260806`
- Линия/фаза: `server operations / Hermes coder canonical production release`
- Статус: `частично`
- Ветка: `fix/hermes-release-git-ownership`
- Базовый commit: `47c14b330161bec0adb269fa320449f2e39a3454`
- Связанные PR и release evidence: `#648`, deploy run `31050534838`

## Перед началом

### Цель

Не позволять root-required canonical release изменять ownership production Git
metadata и тем самым блокировать последующие non-root deploy workflow runs.

### Исходный контекст

После production canonical release attempt скрипт `release.sh` выполнял
`git fetch` в `/srv/velvet` под root. В результате `.git/index` снова стал
root-owned, хотя ранее ownership уже был восстановлен владельцу `velvet`.

Fresh exact-main deploy run `31050534838` подтвердил release ref и secrets, но
остановился до создания detached worktree и до runtime changes:

```text
fatal: .git/index: index file open failed: Permission denied
```

Следовательно, повторный ручной `chown` без исправления скрипта лишь временно
устраняет симптом и будет снова отменён следующим root release.

### Планируемый объём

- оставить privileged systemd, Docker и AppArmor операции под root;
- выполнять Git fetch/rev-parse production checkout только как application user;
- валидировать существование application user до release mutation;
- regression-test отсутствие bare root Git fetch в canonical release;
- не менять volumes, auth, ledger, workspaces, secrets или database state;
- слить только после зелёного required CI.

### Критерии готовности

- canonical release не меняет ownership `/srv/velvet/.git`;
- exact-main verification выполняется от `velvet`;
- shell syntax и release contracts зелёные;
- все required CI contexts зелёные;
- production ownership repair выполняется один раз перед fresh release.

### Риски и ограничения

- production `.git/index` уже требует однократного ownership repair;
- deploy workflow всё ещё не имеет разрешённого non-interactive sudo;
- production systemd unit должен оставаться runtime-masked до нового release;
- fresh release создаётся только от нового current main.

## После завершения

### Фактически сделано

- введён `HERMES_CODERS_APP_USER`, default `velvet`;
- canonical release валидирует application user через `id`;
- production Git fetch выполняется через `runuser -u "$APP_USER"`;
- `origin/main` читается тем же application user;
- удалён root `cd /srv/velvet` + bare `git fetch` path;
- добавлен regression contract для app-user Git ownership boundary.

### Риски и ограничения

- production acceptance ещё не выполнен;
- existing root-owned Git metadata должно быть исправлено вручную один раз;
- workflow sudo contract остаётся отдельной задачей;
- временные compatibility files остаются до canonical acceptance.

### Миграции и совместимость

- database migrations отсутствуют;
- persistent runtime state не изменяется;
- release CLI и environment contract обратно совместимы;
- alternate app user можно задать через `HERMES_CODERS_APP_USER`.

### Проверки

Добавлены проверки для:

- `runuser` Git fetch production checkout;
- `runuser` exact-main rev-parse;
- отсутствия прежнего bare root Git fetch;
- существующего shell syntax contract release script.

### PR и commit

- ветка: `fix/hermes-release-git-ownership`;
- base: `47c14b330161bec0adb269fa320449f2e39a3454`;
- PR и merge commit фиксируются после required CI.

### Незавершённое

- пройти required CI;
- выполнить squash merge;
- однократно восстановить ownership `/srv/velvet/.git`;
- создать fresh exact-current-main release;
- снять runtime mask непосредственно перед manual canonical release;
- подтвердить canonical runtime и удалить temporary compatibility files.

### Следующий шаг

Открыть draft PR, дождаться required CI и выпустить только свежий current main.
