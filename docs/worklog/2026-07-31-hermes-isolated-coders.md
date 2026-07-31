# 2026-07-31 — Изолированные Hermes Coder для Velvet и Max

- Дата: `2026-07-31`
- ID: `hermes-isolated-coders`
- Линия/фаза: `server operations`
- Статус: `завершено`
- Ветка: `infra/hermes-isolated-coders`
- Базовый commit: `2e7250e5cea188aa841ff8e5ffab43c619a715eb`

## Перед началом

### Цель

Разделить работу кодирующих Hermes-агентов по проектам Velvet и Romatic Club Max, чтобы каждый агент имел собственный Telegram gateway, Git checkout, GitHub credential, состояние Hermes и read-only доступ только к своей production-базе.

### Исходный контекст

Общий Hermes Operator продолжил старую задачу Velvet, когда пользователь запросил изменение объекта Max. Один процесс имел смешанный контекст и не обладал жёсткой технической границей между проектами. Production PostgreSQL уже получил отдельные read-only роли `hermes_velvet_ro` и `hermes_max_ro`, резервные копии были созданы и проверены.

Модельный маршрут предварительно проверен вручную через Telegram:

```text
gpt-5.4-mini -> OK
gpt-5.6-terra -> OK
gpt-5.6-luna -> OK
```

`gpt-5.3-codex-spark` дважды вернул `403 Insufficient account balance` на разных API-токенах и был исключён из схемы.

### Планируемый объём

- создать два независимых Hermes Coder gateway;
- не монтировать production checkout, production `.env`, Docker socket и PostgreSQL volumes;
- выдать каждому coder отдельные Telegram и fine-grained GitHub credentials;
- подключить каждый coder только к своей read-only роли PostgreSQL;
- изолировать coder-контейнеры от production Docker networks;
- зафиксировать модельную цепочку `mini -> terra -> luna`;
- добавить installer, preflight, systemd unit, runbook и regression-контракт.

### Критерии готовности

- Velvet-coder видит только checkout `Stellmaria/Velvet`;
- Max-coder видит только checkout `Stellmaria/romatic_club_bot_max`;
- coder-контейнеры не состоят в `velvet_backend` и `romaticclub_default`;
- доступ к PostgreSQL идёт через отдельные внутренние DB-сети и минимальные TCP-прокси;
- DB identity соответствует `hermes_velvet_ro@velvet` и `hermes_max_ro@card_hunter`;
- одинаковые Telegram или GitHub токены блокируются preflight;
- основная модель `gpt-5.4-mini`, усиленная `gpt-5.6-terra`, резервная `gpt-5.6-luna`;
- gateway не запускаются до заполнения отдельных credentials.

### Риски и ограничения

Read-only PostgreSQL не позволяет агентам самостоятельно применять production-миграции или менять данные. Такие операции остаются отдельным контролируемым этапом после проверки и явного разрешения. TCP-прокси ограничивает сетевой маршрут до PostgreSQL, но не заменяет ограничения самой DB-роли. Секреты внутри coder-контейнера технически доступны процессу агента, поэтому каждому проекту выдаются отдельные минимальные credentials без доступа к соседнему репозиторию.

## После завершения

### Фактически сделано

Добавлен отдельный стек `deploy/hermes-coders`:

- `hermes-coder-velvet` с отдельными `/opt/data` и `/workspace`;
- `hermes-coder-max` с отдельными `/opt/data` и `/workspace`;
- `velvet-db-proxy` и `max-db-proxy`, которые одни подключаются к production networks;
- внутренние сети `velvet-db` и `max-db` без внешнего egress;
- общая egress-сеть только для Telegram, GitHub и Byesu;
- derived Hermes image с `gh`, `jq`, `make` и PostgreSQL client;
- project-specific `SOUL.md` с запретом смешивания задач и репозиториев;
- конфигурация моделей `gpt-5.4-mini -> gpt-5.6-terra -> gpt-5.6-luna`;
- идемпотентный `install.sh`;
- `preflight.py` для проверки secret modes, отдельных токенов, checkout и DB identity;
- `hermes-coders.service` для systemd;
- подробный runbook и regression-контракт.

Installer копирует из Hermes Operator только два модельных ключа. Telegram и GitHub credentials оператора не копируются. Gateway намеренно не запускаются до заполнения отдельных credentials.

### Миграции и совместимость

SQL-миграций нет. Схемы production-баз, роли владельцев, текущие bot-контейнеры и Hermes Operator не изменяются. Стек использует существующие external networks `velvet_backend` и `romaticclub_default`, но coder-контейнеры к ним напрямую не подключаются. Применение требует только Docker Compose, установки systemd unit и двух отдельных Telegram/GitHub credential sets.

### Проверки

Добавлен `tests/test_hermes_coders_contract.py`, который проверяет:

- отсутствие Docker socket и production mounts;
- отсутствие прямых production networks у coder-контейнеров;
- сетевой мост только через DB-прокси;
- зафиксированный GPT-маршрут без `gpt-5.3-codex-spark`;
- обязательные read-only identities и отдельные токены;
- порядок `preflight -> compose config -> compose up` в systemd;
- синтаксис Python и Bash;
- pinned Hermes image и наличие GitHub/PostgreSQL tooling.

Ручной production smoke будет выполнен после слияния и заполнения отдельных Telegram/GitHub credentials.

### PR и commit

- PR: `#500`
- Ветка: `infra/hermes-isolated-coders`
- Основной worklog commit обновляется в рамках того же PR.

### Незавершённое

До production-запуска остаётся:

- дождаться зелёного CI и слить PR `#500`;
- обновить `/srv/velvet` до нового `main`;
- выполнить `sudo bash deploy/hermes-coders/install.sh`;
- создать два отдельных Telegram bot token;
- создать два отдельных fine-grained GitHub token, каждый только для своего репозитория;
- выполнить preflight, включить systemd unit и провести Telegram smoke;
- проверить read-only DB identity из обоих coder-контейнеров.

### Следующий шаг

Дождаться обязательных GitHub checks, исправить найденные contract-ошибки, слить PR только после зелёного CI и затем перейти к безопасной установке на VPS без перезапуска production-ботов.
