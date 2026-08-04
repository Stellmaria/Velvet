# Сессия: изолированный production release Hermes coder

- Дата: `2026-08-04`
- ID: `hermes-coder-production-release-20260804`
- Линия/фаза: `server operations / Hermes coder deployment`
- Статус: `частично`
- Ветка: `ops/hermes-coder-production-release`
- Базовый commit: `6aa4f49ae27725e1bdc26de52c94fedeb5562d47`
- Связанные PR и issue: `#597`, `#602`, `#592`

## Перед началом

### Цель

Выкатить terminal-status guard Hermes coder без полного production deployment,
перезапуска bot-контейнера и применения накопившихся SQL migrations.

### Исходный контекст

- terminal-status guard слит в `main` как
  `6aa4f49ae27725e1bdc26de52c94fedeb5562d47`;
- exact-head CI для PR `#597` прошёл targeted Hermes tests, security, CodeQL,
  branch protection и Hermes-only Docker build;
- основной `deploy/server/deploy.sh` обновляет весь checkout и перезапускает bot,
  supervisor и Krita, поэтому он слишком широк для Hermes-only изменения;
- production checkout ранее использовался параллельной работой и не должен
  переписываться или очищаться ради этого release;
- `hermes-coders.service` остаётся failed из-за отдельного nested `bwrap --proc`
  smoke defect, хотя два coder-контейнера работают healthy с `init=true`;
- bot restart может применить накопившиеся migrations, что не входит в scope.

### Планируемый объём

- добавить отдельный production workflow для Hermes coder;
- разрешать release только exact commit текущего `main`;
- получать source через detached Git worktree вне `/srv/velvet` checkout;
- использовать существующие Compose security files и host bwrap override;
- пересоздавать только `hermes-coder-velvet` и `hermes-coder-max`;
- не пересобирать неизменившийся coder image;
- проверять health, restart count, `init`, mounted source SHA и zombies;
- при любой ошибке пересоздавать оба контейнера из прежнего compose source.

### Критерии готовности

- workflow и regression contract проходят GitHub CI;
- release ref указывает на exact current `main`;
- production bot, PostgreSQL, supervisor и Krita не затрагиваются;
- SQL migrations не запускаются;
- production checkout не получает reset, clean или path checkout;
- оба coder-контейнера после release healthy, restart count `0`, `init=true`;
- `/app/codex_tier_runner.py` в обоих контейнерах совпадает с exact release source;
- host и container zombie count равен нулю;
- rollback возвращает прежний compose source при failed health verification.

## После завершения

### Фактически сделано

- добавлен workflow `.github/workflows/deploy-hermes-coders.yml`;
- workflow поддерживает explicit manual dispatch и строго именованный release ref;
- exact SHA повторно сверяется с `origin/main` и на GitHub runner, и на сервере;
- source размещается в `/srv/hermes-coders/releases/<sha>` через detached worktree;
- existing production checkout не переключается и не очищается;
- Compose использует `compose.yaml`, `compose.runtime.yaml`,
  `compose.security.yaml` и существующий `compose.bwrap.override.yaml`;
- deployment выполняет `up -d --no-deps --no-build --force-recreate` только для
  двух coder services;
- workflow сохраняет прежний compose source и image IDs для fail-closed rollback;
- post-release checks подтверждают health, restart count, init/reaper, image ID,
  bind-mounted source path, source SHA и отсутствие zombies;
- добавлен contract test, запрещающий full deploy, migrations, `git reset`,
  `git clean` и `docker compose down` в этом workflow.

### Риски и ограничения

- release worktree должен сохраняться, пока контейнеры используют его bind mount;
- workflow зависит от существующих production SSH secrets и environment policy;
- первый запуск release ref проверяет фактическую генерацию push event GitHub;
- systemd unit не переводится в active и nested bwrap smoke этим изменением не
  исправляется;
- workflow не выполняет coder run acceptance test, чтобы не создавать production
  задания; проверяется только runtime health и exact mounted source;
- cleanup старых detached worktrees требует отдельной retention policy и не
  выполняется автоматически.

### Миграции и совместимость

- migrations отсутствуют;
- PostgreSQL не запускается и не перезапускается;
- bot image и GHCR publish pipeline не используются;
- coder image ID обязан остаться прежним, меняется только bind-mounted runner;
- Compose project name и существующие volume/network contracts сохраняются;
- sandbox, capabilities, `no-new-privileges`, bwrap override и `init=true`
  сохраняются;
- production API и persisted run schema не меняются.

### Проверки

- workflow syntax и policy проверяются GitHub Actions;
- `tests/test_hermes_coder_deploy_workflow_contract.py` проверяет exact-main
  release, detached worktree, узкий service scope, sandbox preservation,
  mounted-source SHA, zombie checks и rollback;
- после merge создаётся release ref
  `release/hermes-coders-<exact-current-main-sha>`;
- production workflow обязан завершиться success до закрытия операции.

### PR и commit

- release workflow PR создаётся из ветки
  `ops/hermes-coder-production-release`;
- окончательные PR, merge commit и release run фиксируются после зелёного CI.

### Незавершённое

- открыть PR с workflow, contract test и worklog;
- дождаться exact-head required checks;
- выполнить merge;
- создать exact release branch от нового current `main`;
- проверить production workflow и post-release container state;
- после успешного rollout закрыть operational часть issue `#592`;
- nested bwrap systemd smoke оставить отдельной задачей.

### Следующий шаг

Открыть PR, пройти required checks, слить workflow и создать exact release ref,
который запустит изолированный production rollout двух Hermes coder containers.
