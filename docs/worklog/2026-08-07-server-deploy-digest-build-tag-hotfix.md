# Сессия: Server deploy digest build tag hotfix

- Дата: `2026-08-07`
- ID: `server-deploy-digest-build-tag-hotfix-20260807`
- Линия/фаза: `Velvet / production deploy / hotfix`
- Статус: `частично`
- Ветка: `hotfix/hermes-coders-preserve-exec-modes-20260807`
- Базовый commit: `0fbeb2705ab171e326ad2f62d40d709c9648fcba`

## Перед началом

### Цель

Устранить подтверждённый production update failure `failed to solve: build tag cannot contain a digest`, сохранив immutable `VELVET_IMAGE=@sha256` в production config для обычных запусков и используя отдельный buildable local tag только в fallback-сборке без `VELVET_DEPLOY_IMAGE`.

### Исходный контекст

Protected Server Supervisor diagnostic для operation `27e62156ffd1428d` доказал полный порядок событий: server preflight прошёл, PostgreSQL dump создан и проверен, checkout переключился на `8282a8c0c6b7143caef8d8b26f4def7b55c4e9d6`, supervisor-proxy успешно собрался, после чего fallback `docker compose build --pull bot` завершился ошибкой `build tag cannot contain a digest`. `deploy.sh` затем запустил rollback и вернул checkout на `0dceb104a8d5c6a1a25dda07c708b916f2e9439f`.

`docker-compose.server.yml` задаёт `bot.image` как `${VELVET_IMAGE:-velvet-bot:local}`. В production `.env.server` переменная может намеренно содержать immutable `ghcr.io/stellmaria/velvet@sha256:...`. При отсутствии явного `VELVET_DEPLOY_IMAGE` deploy script раньше оставлял это значение активным и просил Compose собрать `bot`, из-за чего digest reference использовался как output tag и BuildKit отклонял сборку.

### Планируемый объём

- не менять production `.env.server` и immutable image policy;
- только в fallback local-build branch вычислять `velvet-bot:deploy-${target_sha:0:12}`;
- экспортировать этот tag как `VELVET_IMAGE` до `docker compose build --pull bot`;
- сохранить тот же tag для последующего `up -d --no-deps bot` в рамках текущего deploy process;
- не менять verified-image branch с `VELVET_DEPLOY_IMAGE`;
- не менять rollback priority: exact running image tag -> previous verified digest -> local rebuild;
- добавить regression contract на порядок local tag override до build.

### Критерии готовности

- protected CI зелёный на exact PR head;
- fallback build не наследует digest-form `VELVET_IMAGE` как output tag;
- verified immutable image branch остаётся без изменений по смыслу;
- rollback contract и health/smoke gates сохраняются;
- после merge owner-authorized production update достигает terminal `success` либо раскрывает новый конкретный blocker, но не повторяет `build tag cannot contain a digest`.

### Риски и ограничения

Fallback deploy собирает локальный application image на production host и поэтому не обладает supply-chain свойствами explicit `VELVET_DEPLOY_IMAGE`. Это уже существующий режим deploy script; hotfix только делает его технически совместимым с production config, где default `VELVET_IMAGE` pinned к digest. Канонический путь с переданным verified digest не ослабляется.

## После завершения

### Фактически сделано

- `deploy/server/deploy.sh`: fallback branch теперь задаёт `local_build_image=velvet-bot:deploy-${target_sha:0:12}`, экспортирует его через `VELVET_IMAGE` и только затем запускает Compose build;
- комментарий фиксирует причину override: digest допустим для pull/run, но не для build output tag;
- `tests/test_server_supervisor_contract.py`: добавлен regression, проверяющий наличие local tag и то, что override расположен до `build --pull bot`.

### Миграции и совместимость

Миграций данных нет. Production env schema не меняется. `VELVET_DEPLOY_IMAGE` по-прежнему принимает только immutable GHCR digest; fallback branch использует процесс-local override и не переписывает `.env.server`.

### Проверки

Требуется полный protected CI на exact branch head. После merge production update должен выполняться через существующий Server Supervisor contract с pre-deploy dump, health/smoke и rollback gates.

### PR и commit

Из-за блокировки создания нового ref GitHub connector используется уже merged feature branch, чей tree после PR #695 совпадал с current `main`. Перед новым PR обязателен compare с current `main`; допустимый diff должен содержать только `deploy/server/deploy.sh`, `tests/test_server_supervisor_contract.py` и этот worklog. Merge только exact reviewed head после terminal green protected CI.

### Следующий шаг

Проверить branch diff, открыть отдельный PR, дождаться protected CI и merge. Затем получить exact current main SHA и повторить production rollout через Каэля: один `velvet update` -> terminal success -> clean checkout -> `reconcile coders` -> health -> typed read-only canary.

### Незавершённое

- проверить diff относительно current `main`;
- открыть отдельный PR;
- дождаться protected CI;
- merge exact head;
- выполнить owner-authorized production update;
- выполнить terminal `reconcile coders`;
- подтвердить `coderctl health all` и typed canary.