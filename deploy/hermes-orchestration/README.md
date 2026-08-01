# Hermes Coder Orchestration

Этот слой связывает главный `@VelvetHermesBot` с двумя изолированными coder-агентами:

- Velvet → `@velvet_private_coder_bot` → `Stellmaria/Velvet`;
- Max → `@romatic_max_coder_bot` → `Stellmaria/romatic_club_bot_max`.

Главный Hermes получает возможность поставить задачу, сохранить её в журнале, опрашивать статус, дождаться результата и затем независимо проверить созданный pull request и CI. Coder-агенты по-прежнему не получают Docker socket, systemd, production checkout, production `.env` или право управлять runtime.

## Архитектура

```text
@VelvetHermesBot
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

## Разрешённый цикл

1. Главный Hermes получает запрос владельца или очищенный аварийный инцидент.
2. Собирает read-only `status` и `logs` через `opsctl.py`.
3. Передаёт минимальную очищенную задачу соответствующему coder через `coderctl.py`.
4. Coder создаёт отдельную ветку, вносит исправление, запускает тесты, делает push и создаёт один PR.
5. Главный Hermes ждёт terminal status и проверяет PR, diff, CI и конфликты независимо от отчёта coder.
6. Владелец получает Telegram-отчёт с task/run/PR/tests/blocker.
7. Merge, update, restart и rollback остаются запрещены без явного разрешения владельца.

## Команды главного Hermes

```bash
python /opt/data/tools/coderctl.py health all
python /opt/data/tools/coderctl.py submit velvet --source owner-request --task "<задача>"
python /opt/data/tools/coderctl.py submit max --source owner-request --task "<задача>"
python /opt/data/tools/coderctl.py status <task_id-or-run_id>
python /opt/data/tools/coderctl.py wait <task_id-or-run_id>
python /opt/data/tools/coderctl.py list --limit 20
python /opt/data/tools/coderctl.py stop <task_id-or-run_id>
```

## Предварительные условия

До установки должны работать:

- `hermes-operator-control.service`;
- основной контейнер Hermes;
- оба coder-контейнера и их read-only DB proxies;
- отдельные Telegram и GitHub credentials coder-агентов;
- `/srv/hermes-operator-control/operator.env`;
- `/srv/hermes-coders/secrets/velvet.env` и `max.env` с режимом `0600`.

## Установка

После merge и обновления `/srv/velvet`:

```bash
cd /srv/velvet
sudo bash deploy/hermes-orchestration/install.sh
```

Installer:

1. создаёт internal-сеть `hermes-agent-control`;
2. генерирует разные `API_SERVER_KEY` для coder-агентов, если они ещё не заданы;
3. создаёт `/srv/hermes-operator-control/coders.env` с режимом `0600`;
4. устанавливает `coderctl.py`, managed SOUL и журнал задач в data основного Hermes;
5. обновляет SOUL обоих coder-агентов;
6. выполняет coder preflight;
7. пересоздаёт только coder/router-контейнеры и перезапускает основной Hermes;
8. проверяет health router и выводит состояния стеков.

Секретные значения не печатаются.

## Проверка

На сервере:

```bash
cd /srv/velvet

docker compose \
  --env-file .env.server \
  -f docker-compose.server.yml \
  --profile agent \
  exec -T hermes \
  python /opt/data/tools/coderctl.py health all
```

Ожидаются успешные capabilities для `velvet` и `max`.

Проверка журналирования без ручного чтения token-файлов:

```bash
docker compose \
  --env-file .env.server \
  -f docker-compose.server.yml \
  --profile agent \
  exec -T hermes \
  python /opt/data/tools/coderctl.py list --limit 5
```

## Автоматические инциденты Velvet

Автоматическая передача повторных падений включается только серверными переменными:

```env
HERMES_INCIDENT_ENABLED=true
HERMES_BASE_URL=http://hermes:8642
HERMES_API_KEY=<тот же внутренний ключ, что API_SERVER_KEY основного Hermes>
```

После включения Supervisor отправляет главному Hermes очищенный пакет инцидента. Hermes может подготовить coder-задачу и PR, но не может самостоятельно слить его или изменить production. После terminal status Supervisor отправляет результат в настроенный Telegram log/owner chat.

Max поддерживает ручную маршрутизацию через главный Hermes. Автоматический watcher Max требует отдельного связанного изменения в репозитории `Stellmaria/romatic_club_bot_max`.

## Аварийная остановка

Остановка router без удаления данных:

```bash
cd /srv/velvet/deploy/hermes-operator
HERMES_CODER_ROUTER_ENV_FILE=/srv/hermes-operator-control/coders.env \
  docker compose -f compose.yaml stop hermes-coder-router
```

Журнал, workspaces, coder data и secrets не удалять. Не использовать `down -v`.
