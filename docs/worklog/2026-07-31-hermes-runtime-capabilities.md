# 2026-07-31 — Hermes runtime capabilities

- Дата: 2026-07-31
- ID: hermes-runtime-capabilities
- Линия/фаза: hotfix/эксплуатация вне фаз — Hermes VPS bootstrap
- Статус: завершено
- Ветка: `fix/hermes-runtime-capabilities`
- Базовый commit: `0ca722b1b432af3803865334c335bee1200c6a8b`
- PR: pending

## Перед началом

### Цель

Разрешить официальному Hermes Agent image выполнить обязательный root-init через s6-overlay, не снимая контейнерную изоляцию и не предоставляя ему широкие Linux capabilities.

### Исходный контекст

После удаления Docker `init: true` s6-overlay корректно стал PID 1, но container init завершался ошибками `unable to set supplementary group list: Operation not permitted` и `can't cd to /opt/data`. Причина: сервис Hermes сохранял `cap_drop: ALL`, тогда как официальный image запускает `/init` как root, ремапит внутренние UID/GID, меняет владельца `/opt/data`, затем сбрасывает права до пользователя `hermes`.

### Планируемый объём

- сохранить `cap_drop: ALL`;
- вернуть только capabilities, необходимые s6 init: `CHOWN`, `DAC_OVERRIDE`, `FOWNER`, `SETGID`, `SETUID`;
- сохранить `no-new-privileges:true`;
- не добавлять `privileged`, `SYS_ADMIN`, `NET_ADMIN`, Docker socket или production volumes;
- добавить regression-тест deployment contract.

### Критерии готовности

- s6 init может выполнить `setgroups`, UID/GID remap и `chown /opt/data`;
- Hermes остаётся без всех capabilities, кроме пяти явно разрешённых;
- Compose contract запрещает privileged и административные capabilities;
- unit tests, type check и project notes contract проходят.

### Риски и ограничения

Capabilities действуют только внутри контейнера Hermes и только в отношении доступных ему mount points. Hermes по-прежнему не получает Docker socket, production `.env`, PostgreSQL volume или checkout работающего Velvet.

### Стабилизационное обоснование

Изменение не добавляет пользовательский функционал и не включает автоматическую передачу инцидентов. Оно устраняет блокер запуска уже подготовленного изолированного Hermes container.

## После завершения

Статус: завершено.

### Фактически сделано

- для Hermes сохранён `cap_drop: ALL`;
- добавлены только `CHOWN`, `DAC_OVERRIDE`, `FOWNER`, `SETGID`, `SETUID`;
- сохранён `no-new-privileges:true`;
- regression-тест фиксирует точный allowlist capabilities и отсутствие `privileged`, `SYS_ADMIN`, `NET_ADMIN`.

### Изменённые модули и контракты

- `docker-compose.server.yml` — runtime privilege boundary Hermes;
- `tests/test_server_deployment_contract.py` — deployment regression contract;
- `docs/worklog/2026-07-31-hermes-runtime-capabilities.md` — эксплуатационная запись hotfix.

### Миграции и совместимость

SQL-миграции и данные не изменяются. Существующие `.env.hermes`, Telegram token, image digest и `/srv/velvet/data/hermes` сохраняются.

### Проверки

- Compose сохраняет `cap_drop: ALL` и точный capability allowlist;
- тест запрещает privileged, `SYS_ADMIN`, `NET_ADMIN`;
- полный CI запускается на PR.

### PR и commit

PR создаётся из `fix/hermes-runtime-capabilities` в `main`.

### Незавершённое

После слияния необходимо обновить VPS, повторить `hermes model`, затем проверить model smoke, gateway health и Telegram delivery. `HERMES_INCIDENT_ENABLED` остаётся выключенным.

### Следующий шаг

Слить hotfix после зелёного CI, обновить `/srv/velvet` и продолжить интерактивную настройку Hermes без повторного ввода Telegram token.
