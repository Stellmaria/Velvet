# Hermes Operator Control

Этот контур даёт только главному Telegram-агенту `@VelvetHermesBot` безопасное управление runtime двух проектов:

- Velvet: `bot`;
- Romatic Club Max: `bot` и `userbot`.

Кодеры `@velvet_private_coder_bot` и `@romatic_max_coder_bot` в этот контур не подключаются. Они сохраняют отдельные GitHub tokens, workspaces и read-only DB роли из `deploy/hermes-coders`.

## Граница доступа

Главный Hermes не получает:

- Docker socket;
- systemd или root;
- production checkout и `.env`;
- PostgreSQL volumes;
- supervisor tokens;
- token host-side start bridge.

Отдельный `hermes-ops-gateway` хранит два supervisor token и принимает только фиксированные действия. Gateway не публикует host port, работает без capabilities и подключён к:

- существующей сети `velvet_backend`, где видит Velvet `supervisor-proxy` и основной Hermes;
- внутренней общей сети `hermes-supervisor-control`, где видит только Romatic `supervisor-proxy`;
- dedicated Unix socket `/srv/hermes-operator-control/runtime/start.sock`.

Unix socket принадлежит отдельному `hermes-operator-host.service`. Этот host-side процесс работает непривилегированным пользователем `velvet` и принимает только пару `project/service` из фиксированного allowlist. Он не выполняет Git, shell, systemd, update или rollback. Единственная изменяющая команда внутри него: `docker compose up -d <разрешённый-service>` с последующей проверкой running/health.

Для вызовов Hermes получает отдельный client token в `/opt/data/.hermes-ops-client-token`. Этот token не является Docker, SSH, host-start или supervisor credential и работает только с фиксированным gateway API.

## Разрешённые действия

```text
status
logs
start bot
restart bot
start userbot       # только Max
restart userbot     # только Max
update
rollback
```

`start` не подменяется обновлением Git. Он создаёт или запускает только выбранный Compose service, не перезапускает уже работающий healthy-сервис и завершается лишь после runtime-проверки.

`restart`, `update` и `rollback` по-прежнему идут через существующие Server Supervisor проектов.

Произвольные команды, URL, payload, service names и target SHA не принимаются.

## Установка

Перед установкой Romatic checkout должен содержать shared control network в `compose.yaml`.

```bash
cd /srv/velvet
sudo bash deploy/hermes-operator/install.sh
```

Installer:

1. читает только `SUPERVISOR_TOKEN` из `/srv/velvet/.env.server` и `/srv/romatic-club-max/.env`;
2. создаёт отдельные client и host-start tokens и записывает control credentials в `/srv/hermes-operator-control/operator.env` с режимом `0600`;
3. использует internal Docker network `hermes-supervisor-control`, создаваемую Romatic Compose;
4. пересоздаёт только Romatic `supervisor-proxy`, чтобы подключить его к control network;
5. устанавливает `opsctl.py`, отдельный client token и managed SOUL block в Hermes data;
6. устанавливает и запускает `hermes-operator-host.service`, проверяет dedicated Unix socket;
7. устанавливает и запускает `hermes-operator-control.service`;
8. перезапускает только основной Hermes, чтобы он перечитал правила.

## Проверка

В `@VelvetHermesBot`:

```text
Проверь состояние Velvet и Max через opsctl. Ничего не перезапускай.
```

Ожидаемые команды агента:

```bash
python /opt/data/tools/opsctl.py velvet status
python /opt/data/tools/opsctl.py max status
```

Проверка границ:

```bash
systemctl is-active hermes-operator-host.service
systemctl is-active hermes-operator-control.service
stat -c '%a %U %g %n' /srv/hermes-operator-control/runtime/start.sock

docker inspect hermes-operator-control-hermes-ops-gateway-1 \
  --format '{{json .Mounts}} {{json .NetworkSettings.Networks}}'
```

У gateway не должно быть published ports, Docker socket, production checkout или `.env` mounts. Единственный host bind mount gateway должен указывать на `/srv/hermes-operator-control/runtime`. Coder-контейнеры не должны находиться в `hermes-supervisor-control` и не должны получать этот runtime mount.

## Эксплуатация

Изменяющие операции основной Hermes выполняет только после явного указания владельца. После `start` он сразу подтверждает состояние сервиса. После асинхронных `restart`, `update` или `rollback` он опрашивает status до `success` или `error`, а затем отдельно проверяет running/health нужного сервиса.
