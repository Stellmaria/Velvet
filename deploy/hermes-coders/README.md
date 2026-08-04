# Изолированные Hermes Coder для Velvet и Romatic Club Max

Этот стек запускает два независимых chat gateway и два активных Codex runner:

- `hermes-chat-velvet` и `hermes-coder-velvet` работают только с
  `Stellmaria/Velvet`;
- `hermes-chat-max` и `hermes-coder-max` работают только с
  `Stellmaria/romatic_club_bot_max`.

Каждый Codex runner имеет отдельные `$CODEX_HOME`, `$HOME`, workspace, auth и
Brain context. Global `$CODEX_HOME/AGENTS.md` детерминированно объединяет SOUL,
project contract, bounded memory и общие policies; project skills находятся в
`$HOME/.agents/skills`. `context-manifest.json` и preflight защищают от
перепутывания Velvet/Max.

Они не монтируют production checkout, `.env`, Docker socket или PostgreSQL volume. Каждый coder получает отдельные:

- Telegram bot token;
- fine-grained GitHub token;
- Hermes data directory;
- Git workspace;
- read-only PostgreSQL роль;
- внутреннюю DB-сеть;
- `API_SERVER_KEY` для private Runs API.

## Сетевая граница

Coder-контейнеры не подключаются к `velvet_backend` или `romaticclub_default` напрямую. Минимальные TCP-прокси подключены к production-сетям и публикуют только PostgreSQL `5432` во внутренние сети соответствующих кодеров.

```text
hermes-coder-velvet -> velvet-db -> velvet-db-proxy -> velvet_backend -> postgres
hermes-coder-max    -> max-db    -> max-db-proxy    -> romaticclub_default -> postgres
```

Для GitHub, Telegram и Byesu оба coder-контейнера используют отдельную egress-сеть.

Runs API слушает `8642` внутри контейнера, но host ports не публикуются. Доступ к API разрешён только `hermes-coder-router` через external internal-сеть `hermes-agent-control`. Главный Hermes не получает coder API keys.

## Модели

Active Codex route: `luna` для малых задач, `terra` для обычной инженерной
работы, `sol` для architecture/security. Fallback используется только при
capacity/availability error. Legacy chat gateway сохраняет Byesu route из
`config.yaml`.

Telegram aliases:

```text
/model mini
/model terra
/model luna
```

## Предварительные условия

До установки должны существовать read-only env-файлы:

```text
/srv/hermes-coders/secrets/velvet-db.env
/srv/hermes-coders/secrets/max-db.env
```

Поддерживаются два формата:

```env
DATABASE_URL=postgresql://readonly_user:password@postgres:5432/database
```

или:

```env
PGHOST=postgres
PGPORT=5432
PGDATABASE=database
PGUSER=readonly_user
PGPASSWORD=password
```

Preflight требует:

```text
Velvet: user=hermes_velvet_ro, db=velvet
Max:    user=hermes_max_ro, db=card_hunter
```

## Установка без запуска

После слияния PR и обновления `/srv/velvet`:

```bash
cd /srv/velvet
sudo bash deploy/hermes-coders/install.sh
```

Installer:

1. создаёт `/srv/hermes-coders`;
2. клонирует два отдельных workspace;
3. копирует только модельные ключи из `/srv/velvet/.env.hermes`;
4. не копирует Telegram token и GitHub token оператора;
5. компилирует отдельные Hermes/Codex Brain packs и Git credential helper;
6. устанавливает Codex global AGENTS, scoped skills и output JSON schema;
7. добавляет `GH_TOKEN`, bounded compression и loop circuit breaker в оба
   Hermes runtime config;
8. собирает coder и DB-proxy images;
9. устанавливает, но не запускает `hermes-coders.service`.

## Заполнение отдельных токенов

В файлах ниже должны быть разные Telegram, GitHub и API credentials:

```text
/srv/hermes-coders/secrets/velvet.env
/srv/hermes-coders/secrets/max.env
```

Безопаснее открыть каждый через `sudoedit`:

```bash
sudoedit /srv/hermes-coders/secrets/velvet.env
sudoedit /srv/hermes-coders/secrets/max.env
sudo chmod 600 /srv/hermes-coders/secrets/*.env
sudo chown velvet:velvet /srv/hermes-coders/secrets/*.env
```

Fine-grained GitHub token для Velvet ограничивается репозиторием `Stellmaria/Velvet`, а токен Max только `Stellmaria/romatic_club_bot_max`. Минимально нужны Contents и Pull requests read/write. Не выдавать Administration, Actions secrets и доступ к другим репозиториям.

Один Telegram bot token, GitHub token или `API_SERVER_KEY` нельзя использовать в двух coder gateway одновременно. Preflight специально блокирует такую попытку.

Orchestration installer может безопасно сгенерировать разные `API_SERVER_KEY`, не печатая значения:

```bash
sudo bash /srv/velvet/deploy/hermes-orchestration/install.sh
```

## Preflight и запуск

Hermes может атомарно переписать runtime `config.yaml` под UID контейнера во
время миграции схемы. Поэтому systemd перед каждым запуском идемпотентно
восстанавливает `terminal.cwd`, `GH_TOKEN` passthrough, compression и loop
guardrails. Затем preflight проверяет Brain hashes, role/project sentinels,
Codex schema/skills и runtime metadata. Compose-команды и gateway продолжают
выполняться от пользователя `velvet`.

Ручная проверка выполняется в том же порядке:

```bash
sudo python3 \
  /srv/velvet/deploy/hermes-coders/ensure_runtime_config.py \
  /srv/hermes-coders/data/velvet/config.yaml \
  /srv/hermes-coders/data/max/config.yaml

sudo env \
  HERMES_CODERS_ROOT=/srv/hermes-coders \
  python3 /srv/velvet/deploy/hermes-coders/preflight.py

sudo systemctl enable --now hermes-coders.service
sudo systemctl --no-pager --full status hermes-coders.service
```

Проверка контейнеров:

```bash
cd /srv/velvet/deploy/hermes-coders
HERMES_CODERS_ROOT=/srv/hermes-coders \
HERMES_AGENT_CONTROL_NETWORK=hermes-agent-control \
  docker compose --profile velvet --profile max -f compose.yaml ps

HERMES_CODERS_ROOT=/srv/hermes-coders \
HERMES_AGENT_CONTROL_NETWORK=hermes-agent-control \
  docker compose --profile velvet --profile max -f compose.yaml logs --tail=100
```

## Проверка изоляции

Coder-контейнеры должны видеть только egress, свою внутреннюю DB-сеть и `hermes-agent-control`:

```bash
docker inspect hermes-coders-hermes-coder-velvet-1 \
  --format '{{json .NetworkSettings.Networks}}'

docker inspect hermes-coders-hermes-coder-max-1 \
  --format '{{json .NetworkSettings.Networks}}'
```

На coder-контейнерах не должно быть сетей `velvet_backend`, `romaticclub_default` или `hermes-supervisor-control`.

Проверка read-only identity:

```bash
cd /srv/velvet/deploy/hermes-coders

HERMES_CODERS_ROOT=/srv/hermes-coders \
  docker compose --profile velvet -f compose.yaml exec -T hermes-coder-velvet \
  sh -ceu 'psql "$DATABASE_URL" -Atc "select current_user,current_database(),current_setting('"'"'default_transaction_read_only'"'"');"'

HERMES_CODERS_ROOT=/srv/hermes-coders \
  docker compose --profile max -f compose.yaml exec -T hermes-coder-max \
  sh -ceu 'psql "$DATABASE_URL" -Atc "select current_user,current_database(),current_setting('"'"'default_transaction_read_only'"'"');"'
```

Ожидается `on` и соответствующая роль `hermes_*_ro`.

## Telegram smoke

В каждом отдельном боте:

```text
/new
/model mini
Ответь строго одним словом: OK

/new
/model terra
Ответь строго одним словом: OK

/new
/model luna
Ответь строго одним словом: OK
```

Затем дать безопасную задачу только на чтение:

```text
Покажи текущий репозиторий, ветку и статус Git. Ничего не изменяй.
```

Velvet-coder обязан назвать `Stellmaria/Velvet`, Max-coder обязан назвать `Stellmaria/romatic_club_bot_max`.

GitHub CLI проверяется без вывода токена:

```text
Выполни gh auth status и gh repo view для текущего репозитория. Ничего не изменяй и не показывай секреты.
```

## Остановка

```bash
sudo systemctl stop hermes-coders.service
```

Аварийное удаление только контейнеров и сетей, без удаления data/workspaces/secrets:

```bash
cd /srv/velvet/deploy/hermes-coders
HERMES_CODERS_ROOT=/srv/hermes-coders \
HERMES_AGENT_CONTROL_NETWORK=hermes-agent-control \
  docker compose --profile velvet --profile max -f compose.yaml down
```

Не использовать `down -v`: bind-mounted data, workspaces и secrets должны сохраняться.

## Единый router и sandbox

Direct Telegram и delegated Каэлем задачи используют один central tier router.
Direct helper выставляет `source=owner-direct`, Каэль — `source=kael-delegated`;
оба пути получают task/run IDs и routing fields только от router/ledger. При
недоступности router direct helper завершается fail-closed без shell/Git fallback.

Lifecycle обоих coder runner всегда рендерится из трёх слоёв:
`compose.yaml`, `compose.runtime.yaml`, `compose.security.yaml`. Security layer
назначает только runner-процессам enforcing `hermes-codex-bwrap` и custom seccomp.
Runtime smoke проверяет user/mount namespaces, minimal bwrap, read-only Git,
неизменный fingerprint, NoNewPrivs, пустой capability set, named AppArmor,
active seccomp, read-only rootfs и `cryptography==50.0.0` в main Hermes.

Каждый run создаёт отдельный worktree от свежего `origin/main` под
`codex-runs/<project>/workspaces`; cleanup ограничен каталогом конкретного run и
не затрагивает auth, ledger, run history, secrets или approved caches.
