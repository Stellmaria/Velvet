# 2026-08-01 — Ограниченный runtime-контроль для главного Hermes

- Дата: `2026-08-01`
- ID: `hermes-operator-control`
- Линия/фаза: `server operations`
- Статус: `частично`
- Ветка: `agent/hermes-operator-control`
- Базовый commit: `ffa6f5272d321fdcc9864f9172819c357a674f48`

## Перед началом

### Цель

Дать `@VelvetHermesBot` возможность проверять, запускать, перезапускать, обновлять и откатывать Velvet bot, Romatic Max bot и Romatic userbot, не выдавая агенту Docker socket, systemd, production `.env`, SSH или supervisor credentials.

### Исходный контекст

Изолированные кодеры `@velvet_private_coder_bot` и `@romatic_max_coder_bot` уже работают только в собственных Git workspaces с отдельными fine-grained GitHub tokens. Поэтому Max-coder корректно отказался запускать production-сервисы из `/workspace`: в его контейнере отсутствуют Docker daemon, Compose, `.env` и host runtime.

Основной Hermes предназначен для координации кодеров и production-операций, но до этой работы не имел отдельного безопасного пути к обоим server supervisor.

### Планируемый объём

- добавить отдельный fixed-action gateway для главного Hermes;
- не передавать supervisor tokens в Hermes terminal;
- поддержать Velvet `bot`, Max `bot` и Max `userbot`;
- разрешить только status, logs, start, restart, update и rollback;
- запретить произвольные URL, payload, shell и target SHA;
- сохранить coder-контейнеры вне control-сетей и runtime socket;
- добавить installer, systemd units, managed SOUL block и tests.

### Критерии готовности

- основной Hermes вызывает операции через `/opt/data/tools/opsctl.py`;
- gateway не имеет host ports, Docker socket, systemd, production checkout или `.env` mounts;
- upstream supervisor tokens находятся только в отдельном env gateway;
- `start` выполняется отдельным host-side allowlisted bridge и не подменяется update;
- Max supervisor-proxy доступен gateway через internal shared network;
- кодеры не получают новый runtime-доступ;
- после изменяющей операции Hermes проверяет терминальный operation status и running/health сервиса;
- обязательные CI checks проходят.

### Риски и ограничения

Gateway доверяет отдельному client token, сохранённому в data главного Hermes. Этот token не даёт прямого доступа к Docker, host bridge или supervisor и принимается только fixed-action gateway. Host bridge имеет собственный token, доступный только gateway, и принимает только три разрешённых target: Velvet bot, Max bot и Max userbot.

## После завершения

### Фактически сделано

- добавлены `gateway.py`, `opsctl.py` и отдельный hardened Compose;
- gateway принимает только пустой JSON и фиксированные project/action/service;
- ответы upstream рекурсивно очищаются от полей token, password, secret, authorization и API key;
- добавлен `host_start.py`, который выполняет только `docker compose up -d` разрешённого service и проверяет running/health;
- gateway получает только dedicated Unix socket host bridge, но не Docker socket;
- добавлены отдельные client, host-start и upstream supervisor credentials;
- добавлены unprivileged `hermes-operator-host.service` и `hermes-operator-control.service`;
- runtime SOUL обновляется managed-блоком без удаления существующих инструкций;
- coder compose проверяется контрактом на отсутствие operator network и runtime mount;
- открыты связанные draft PR `Stellmaria/Velvet#529` и `Stellmaria/romatic_club_bot_max#15`.

### Миграции и совместимость

SQL-миграций нет. Production compose Velvet не меняется. Для Max требуется совместимое изменение `compose.yaml`, подключающее только `supervisor-proxy` к общей internal control network. `start` не требует изменения существующих Supervisor API.

### Проверки

Добавлены статические security contracts и поведенческие тесты host bridge/Unix protocol без реального Docker. Первый CI-запуск выявил и позволил исправить слишком широкий contract-тест coder-сети и статус worklog. Max PR уже прошёл свой CI. Повторный Velvet CI и server smoke ещё не завершены.

### PR и commit

- Velvet PR: `#529`;
- Max PR: `Stellmaria/romatic_club_bot_max#15`;
- ветка: `agent/hermes-operator-control`.

### Незавершённое

- дождаться зелёного CI Velvet PR после добавления fixed start bridge;
- провести финальный review gateway, host bridge и installer;
- слить сначала Max PR, затем Velvet PR;
- выполнить `sudo bash deploy/hermes-operator/install.sh` на VPS;
- проверить read-only status Velvet bot, Max bot и Max userbot через основной Hermes;
- отдельно smoke-проверить start только на остановленном тестовом/фактически требующем запуска сервисе после явного запроса владельца.

### Следующий шаг

Проверить новый CI. После зелёных обязательных checks выполнить server deployment, затем read-only status smoke. Production start/restart выполнять только по явному запросу владельца.
