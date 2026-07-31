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
- сохранить coder-контейнеры вне control-сетей;
- добавить installer, systemd unit, managed SOUL block и contract tests.

### Критерии готовности

- основной Hermes вызывает операции через `/opt/data/tools/opsctl.py`;
- gateway не имеет host ports, Docker socket, systemd и production mounts;
- upstream supervisor tokens находятся только в отдельном env gateway;
- Max supervisor-proxy доступен gateway через internal shared network;
- кодеры не получают новый runtime-доступ;
- после изменяющей операции Hermes повторно проверяет status;
- обязательные CI checks проходят.

### Риски и ограничения

Gateway доверяет только отдельному client token, сохранённому в data главного Hermes. Этот token не даёт прямого доступа к Docker или supervisor и принимается только fixed-action gateway. Изменяющие операции дополнительно ограничены правилами SOUL и требуют явного запроса владельца.

## После завершения

### Фактически сделано

- добавлены `gateway.py`, `opsctl.py` и отдельный hardened Compose;
- gateway принимает только пустой JSON и фиксированные project/action/service;
- ответы upstream рекурсивно очищаются от полей token, password, secret, authorization и API key;
- добавлен installer, создающий отдельные credentials и проверяющий internal control network;
- добавлен unprivileged systemd unit;
- runtime SOUL обновляется managed-блоком без удаления существующих инструкций;
- coder compose проверяется контрактом на отсутствие operator control network;
- открыты связанные draft PR `Stellmaria/Velvet#529` и `Stellmaria/romatic_club_bot_max#15`.

### Миграции и совместимость

SQL-миграций нет. Production compose Velvet не меняется. Для Max требуется совместимое изменение `compose.yaml`, подключающее только `supervisor-proxy` к общей internal control network.

### Проверки

Добавлен `tests/test_hermes_operator_control_contract.py`. Python compile preflight и type check прошли. Первый CI-запуск выявил и позволил исправить слишком широкий contract-тест coder-сети и статус worklog. Полный повторный CI, Docker build и server smoke ещё не завершены.

### PR и commit

- Velvet PR: `#529`;
- Max PR: `Stellmaria/romatic_club_bot_max#15`;
- ветка: `agent/hermes-operator-control`.

### Незавершённое

- дождаться повторного зелёного CI обоих PR;
- провести review gateway и installer;
- слить сначала Max PR, затем Velvet PR;
- выполнить `sudo bash deploy/hermes-operator/install.sh` на VPS;
- проверить read-only status Velvet bot, Max bot и Max userbot через основной Hermes.

### Следующий шаг

Проверить новый CI после исправлений. После зелёных обязательных checks выполнить server deployment и smoke без перезапуска production-ботов, пока владелец явно не запросит изменяющее действие.
