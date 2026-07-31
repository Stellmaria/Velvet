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
- supervisor tokens.

Отдельный `hermes-ops-gateway` хранит два supervisor token и принимает только фиксированные действия. Gateway не публикует host port, работает без capabilities и подключён к:

- существующей сети `velvet_backend`, где видит Velvet `supervisor-proxy` и основной Hermes;
- внутренней общей сети `hermes-supervisor-control`, где видит только Romatic `supervisor-proxy`.

Для вызовов Hermes получает отдельный client token в `/opt/data/.hermes-ops-client-token`. Этот token не является Docker, SSH или supervisor credential и работает только с фиксированным gateway API.

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

`start` сначала проверяет состояние. Если контейнер существует, но остановлен, используется разрешённый restart. Если контейнер отсутствует, запускается проверяемый deploy gate проекта, который создаёт сервисы и выполняет smoke-проверку.

Произвольные команды, URL, payload и target SHA не принимаются.

## Установка

Перед установкой Romatic checkout должен содержать shared control network в `compose.yaml`.

```bash
cd /srv/velvet
sudo bash deploy/hermes-operator/install.sh
```

Installer:

1. читает только `SUPERVISOR_TOKEN` из `/srv/velvet/.env.server` и `/srv/romatic-club-max/.env`;
2. записывает их в `/srv/hermes-operator-control/operator.env` с режимом `0600`;
3. создаёт internal Docker network `hermes-supervisor-control`;
4. пересоздаёт только Romatic `supervisor-proxy`, чтобы подключить его к control network;
5. устанавливает `opsctl.py`, отдельный client token и managed SOUL block в Hermes data;
6. устанавливает и запускает `hermes-operator-control.service`;
7. перезапускает только основной Hermes, чтобы он перечитал правила.

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

Проверка сети:

```bash
docker inspect hermes-operator-control-hermes-ops-gateway-1 \
  --format '{{json .NetworkSettings.Networks}}'
```

У gateway не должно быть published ports, Docker socket или bind mounts. Coder-контейнеры не должны находиться в `velvet_backend` или `hermes-supervisor-control`.

## Эксплуатация

Изменяющие операции основной Hermes выполняет только после явного указания владельца. После `start`, `restart`, `update` или `rollback` он обязан повторно вызвать `status` и не объявлять успех по одному принятому HTTP-запросу.
