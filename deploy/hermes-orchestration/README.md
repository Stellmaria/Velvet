# Hermes Coder Orchestration

Этот слой связывает главного `@VelvetHermesBot` с двумя изолированными coder-агентами:

- Velvet → `@velvet_private_coder_bot` → `Stellmaria/Velvet`;
- Max → `@romatic_max_coder_bot` → `Stellmaria/romatic_club_bot_max`.

Главный Hermes ставит задачу, фиксирует её tier/risk policy, сохраняет журнал, ждёт результат и независимо проверяет созданный pull request и CI. Coder-агенты не получают Docker socket, systemd, production checkout, production `.env` или право управлять runtime.

## Архитектура

```text
@VelvetHermesBot / Каэль
  └─ coderctl.py
      └─ hermes-coder-router:8878
          ├─ hermes-coder-velvet:8642
          └─ hermes-coder-max:8642
```

- `coderctl.py` использует отдельный client token и хранит журнал в `/opt/data/orchestration/tasks.json`.
- `hermes-coder-router` принимает только фиксированные проекты и маршруты Runs API.
- Router не монтирует Docker socket, production checkout, `.env` или host filesystem.
- API coder-агентов доступен только во внутренней Docker-сети `hermes-agent-control`, без опубликованных портов.
- У каждого coder отдельный `API_SERVER_KEY`; ключи не передаются главному Hermes.

## Каноническая модельная политика

До делегирования Каэль фиксирует:

- `task_type`: `read_only`, `docs`, `code`, `architecture`, `security`, `migration` или `incident`;
- `requested_tier`: `small`, `standard`, `complex` или `high_risk`;
- `risk`: `low`, `medium`, `high` или `critical`;
- `mutation_policy`: `read_only` или `workspace_pr`.

Router отклоняет under-tier комбинации: `medium` требует минимум `standard`,
`high` минимум `complex`, `critical` только `high_risk`; architecture/incident
требуют минимум `complex`, security/migration только `high_risk`. Политика
`read_only` независима от сложности, поэтому high-risk security review может
быть read-only. При этом task type `read_only` всегда запрещает workspace mutation.

Primary Codex routing:

```text
small      -> Luna -> Terra только при capacity
standard   -> Terra
complex    -> Sol -> Terra как degraded route
high_risk  -> Sol -> Terra как degraded route
```

Byesu routing для фактически доступных production token groups:

```text
small general/read-only -> Luna -> Terra
small code              -> Mini -> Terra
standard                 -> Terra
complex/high_risk        -> Terra, degraded=true, review_required=true
```

`Terra -> Luna` для standard/complex запрещён как downgrade. Sol у production Byesu-ключей Velvet и Max не видна через `/v1/models`, поэтому provider Terra для complex/high-risk работает только в изолированном workspace и всегда требует усиленной проверки.

Любая модель, включая Sol, может только менять код в изолированной ветке, запускать тесты, делать commit/push и открывать PR. Ни одна модель не может самостоятельно делать merge, deploy, restart, rollback, менять live production checkout или читать production secrets.

## Разрешённый цикл

1. Каэль получает запрос владельца или очищенный инцидент.
2. Определяет `project`, `task_type`, `requested_tier`, `risk`, `mutation_policy`.
3. Собирает read-only `status` и `logs` через `opsctl.py`, если это требуется.
4. Передаёт минимальную очищенную задачу соответствующему coder через `coderctl.py`.
5. Coder создаёт отдельную ветку, вносит исправление, запускает тесты, делает push и создаёт один PR.
6. Каэль ждёт terminal status и проверяет PR, diff, CI и конфликты независимо от отчёта coder.
7. Владелец получает Telegram-отчёт с task/run/tier/route/PR/tests/blocker.
8. Merge, update, restart и rollback остаются запрещены без явного разрешения владельца.

## Команды главного Hermes

```bash
python /opt/data/tools/coderctl.py health all

python /opt/data/tools/coderctl.py submit velvet \
  --source owner-request \
  --task-type code \
  --tier standard \
  --risk medium \
  --mutation-policy workspace_pr \
  --task "<задача>"

python /opt/data/tools/coderctl.py submit max \
  --source incident \
  --task-type security \
  --tier high_risk \
  --risk critical \
  --mutation-policy workspace_pr \
  --task "<очищенная задача>"

python /opt/data/tools/coderctl.py status <task_id-or-run_id>
python /opt/data/tools/coderctl.py wait <task_id-or-run_id>
python /opt/data/tools/coderctl.py list --limit 20
python /opt/data/tools/coderctl.py stop <task_id-or-run_id>
```

CLI по умолчанию использует безопасный `code/standard/medium/workspace_pr`, чтобы неизвестная coder-задача не была молча отправлена на слишком слабую модель. Более дешёвый `small` и более дорогой `complex/high_risk` Каэль выбирает явно.

## Предварительные условия

До установки должны работать:

- `hermes-operator-control.service`;
- основной контейнер Hermes;
- оба coder-контейнера и их read-only DB proxies;
- отдельные Telegram и GitHub credentials coder-агентов;
- `/srv/hermes-operator-control/operator.env`;
- `/srv/hermes-coders/secrets/velvet.env` и `max.env` с режимом `0600`.

## Установка

После merge и контролируемого обновления `/srv/velvet`:

```bash
cd /srv/velvet
sudo bash deploy/hermes-orchestration/install.sh
```

Installer подготавливает внутреннюю сеть, credentials, managed SOUL, `coderctl.py`, journal и runtime. Секретные значения не печатаются.

## Проверка

```bash
cd /srv/velvet

docker compose \
  --env-file .env.server \
  -f docker-compose.server.yml \
  --profile agent \
  exec -T hermes \
  python /opt/data/tools/coderctl.py health all
```

Capabilities должны показывать `primary_routes_by_tier`, `provider_fallback.routes_by_tier`, `downgrade_allowed=false` и `live_production_mutation=false` для Velvet и Max.

Проверка журналирования:

```bash
docker compose \
  --env-file .env.server \
  -f docker-compose.server.yml \
  --profile agent \
  exec -T hermes \
  python /opt/data/tools/coderctl.py list --limit 5
```

## Автоматические инциденты Velvet

Автоматический watcher передаёт только очищенный пакет инцидента. Для incident по умолчанию требуется `complex/high` либо явный `high_risk/critical`. Hermes может подготовить coder-задачу и PR, но не может самостоятельно слить его или изменить production.

Max поддерживает ручную маршрутизацию через главного Hermes. Автоматический watcher Max требует отдельного связанного изменения в `Stellmaria/romatic_club_bot_max`.

## Аварийная остановка

Остановка router без удаления данных:

```bash
cd /srv/velvet/deploy/hermes-operator
HERMES_CODER_ROUTER_ENV_FILE=/srv/hermes-operator-control/coders.env \
  docker compose -f compose.yaml stop hermes-coder-router
```

Журнал, workspaces, coder data и secrets не удалять. Не использовать `down -v`.
