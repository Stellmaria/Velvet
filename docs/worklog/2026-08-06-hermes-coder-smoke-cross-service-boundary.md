# Сессия: Hermes coder smoke cross-service boundary

- Дата: `2026-08-06`
- ID: `hermes-coder-smoke-cross-service-boundary-20260806`
- Линия/фаза: `server operations / Hermes coder canonical production release`
- Статус: `частично`
- Ветка: `fix/hermes-coder-smoke-cross-service-boundary`
- Базовый commit: `094c77bf55f66c04d9e3e91824dba5e33bb38a5f`
- Связанные PR и release evidence: `#648`, `#649`, `#651`, `#653`, release `094c77bf55f66c04d9e3e91824dba5e33bb38a5f`

## Перед началом

### Цель

Устранить ложный rollback canonical Hermes coder release, вызванный проверкой
версии Python dependency в независимо развёрнутом основном Hermes container.

### Исходный контекст

Canonical release `094c77bf55f66c04d9e3e91824dba5e33bb38a5f` успешно прошёл
idle gate, Brain Vault, launcher staging, immutable image pinning, coder и
sandbox preflight. Оба проекта затем полностью прошли runtime smoke:

```text
CHAT_OK, CODEX_AUTH_OK, PROJECT_AUTH_OK, LAUNCHER_OK,
DISPOSABLE_DOCKER_OK, BASE_RO_OK, PUSH_OK, NO_ZOMBIES
```

Единственным отказом была проверка независимо развёрнутого main Hermes image:

```text
main Hermes cryptography mismatch: expected 50.0.0, actual 46.0.7
```

Repository manifest и hash lock уже закрепляют `cryptography==50.0.0`, а root
Dockerfile устанавливает именно lock. Production main Hermes image не был
пересобран после обновления dependency, но это не является дефектом Hermes
coder runtime и не должно инициировать его rollback.

Rollback восстановил previous current link, launcher release и image IDs.
Coder, chat и database proxy containers после rollback работают healthy с
нулевыми restart count. Unit возвращён в disabled/runtime-masked состояние.

### Планируемый объём

- удалить main Hermes dependency probe из `deploy/hermes-coders/runtime_smoke.py`;
- сохранить все coder/chat, GitHub, launcher, isolation, seccomp и AppArmor probes;
- не менять root `requirements.txt`, `requirements.lock`, Dockerfile или server deployment;
- добавить regression contract, запрещающий cross-service paths и dependency probe;
- слить только после полного зелёного required CI.

### Критерии готовности

- coder runtime smoke не использует `/srv/velvet/.env.server`;
- coder runtime smoke не использует `/srv/velvet/docker-compose.server.yml`;
- `verify_main_cryptography`, `CRYPTOGRAPHY_VERSION` и `importlib.metadata` отсутствуют;
- все Hermes/Codex runtime probes остаются без изменений;
- required protected-branch CI зелёный;
- production acceptance выполняется fresh exact-current-main release.

## После завершения

### Фактически сделано

- удалён cross-service main Hermes dependency probe из coder runtime smoke;
- сохранены gateway readiness, GitHub push, Codex authentication, launcher,
  disposable Docker, read-only base, no-new-privileges, capabilities, seccomp,
  AppArmor и zombie-process проверки;
- добавлен отрицательный source contract против server compose/env paths и
  `cryptography` dependency probe;
- root dependency pin `cryptography==50.0.0` не изменялся;
- production persistent state этим PR не изменялся.

### Риски и ограничения

- этот PR не обновляет independently deployed main Hermes image;
- main server dependency compliance остаётся обязанностью server deployment и
  его собственного acceptance contract;
- deploy workflow всё ещё требует интерактивный sudo для root release;
- production coder unit остаётся disabled/runtime-masked до fresh release.

### Миграции и совместимость

Миграций базы, volumes, auth, secrets, ledger или workspaces нет. Изменяется
только граница canonical coder release smoke. Main Hermes dependency pin и
server image lifecycle остаются без изменений.

### Проверки

- compile и type checks для изменённого Python source;
- regression assertions против `.env.server`, server compose,
  `verify_main_cryptography`, `CRYPTOGRAPHY_VERSION`, `importlib.metadata` и
  `cryptography` в coder smoke;
- существующие Hermes runtime, systemd и AppArmor contracts;
- полный protected-branch required CI после открытия PR.

### PR и commit

- PR создаётся из `fix/hermes-coder-smoke-cross-service-boundary`;
- base: `094c77bf55f66c04d9e3e91824dba5e33bb38a5f`;
- итоговый head и merge commit фиксируются после required CI.

### Незавершённое

- открыть PR и дождаться required CI;
- выполнить squash merge без обхода branch protection;
- создать fresh release branch от нового current main;
- повторить canonical production acceptance;
- подтвердить exact release link, healthy containers и canonical source mounts;
- удалить temporary compatibility artifacts только после acceptance.

### Следующий шаг

Открыть draft PR, дождаться полного required CI, выполнить squash merge и
повторить canonical release с exact-current-main SHA.
