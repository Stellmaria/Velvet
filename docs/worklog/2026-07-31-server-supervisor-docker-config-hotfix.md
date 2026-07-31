# 2026-07-31 — Writable Docker config для Server Supervisor

- Дата: `2026-07-31`
- ID: `server-supervisor-docker-config-hotfix`
- Линия/фаза: `server operations`
- Статус: `завершено`
- Ветка: `agent/server-supervisor-docker-config-hotfix`
- Базовый commit: `164c39bf91e45e2bc10700808ab9f2b9dca2f8b5`

## Перед началом

### Цель

Исправить реальное обновление Velvet из Telegram, которое после успешных fetch, backup и проверки dump падало при Docker build из-за попытки Compose записать buildx metadata в read-only домашний каталог пользователя `velvet`.

### Исходный контекст

Server Supervisor работает под systemd с `ProtectHome=read-only`. После исправления общего deploy-lock обновление дошло до `docker compose build`, но Docker Compose попытался создать временный файл в `/home/velvet/.docker/buildx/refs/...` и получил `Read-only file system`. Автоматический rollback вернул код на предыдущий commit, PostgreSQL dump был сохранён, бот и база остались здоровы.

### Планируемый объём

- не ослаблять `ProtectHome`;
- задать отдельный writable `DOCKER_CONFIG` внутри persistent runtime;
- отключить Compose Bake для server deploy;
- создавать каталог Docker config как при installer, так и внутри `deploy.sh`;
- сохранить общий `/tmp/velvet-deploy.lock`;
- добавить regression-контракт.

### Критерии готовности

- Telegram update не пишет в `/home/velvet/.docker`;
- Docker build работает внутри systemd sandbox;
- deploy и rollback используют одинаковый writable Docker config;
- SSH deploy сохраняет совместимость;
- `ProtectHome=read-only`, `NoNewPrivileges=true` и отсутствие Docker socket у бота сохраняются;
- CI полностью зелёный.

### Риски и ограничения

Первое обновление с production commit до hotfix всё ещё запускается старым `deploy.sh`, поэтому до его применения systemd unit необходимо один раз вручную дополнить `DOCKER_CONFIG` и `COMPOSE_BAKE=false`. После успешного обновления репозиторий и установленный unit будут согласованы.

## После завершения

### Фактически сделано

- systemd unit получил `DOCKER_CONFIG=/srv/velvet/data/runtime/docker-config`;
- для systemd runtime установлен `COMPOSE_BAKE=false`;
- installer создаёт Docker config каталог, назначает владельца `velvet` и права `0700`;
- `deploy.sh` самостоятельно выбирает writable Docker config, создаёт его и экспортирует настройки до первого Compose build;
- защита `ProtectHome=read-only` не ослаблена;
- regression-тесты проверяют unit, installer и deploy contract.

### Миграции и совместимость

SQL-миграций нет. PostgreSQL dump, rollback, Telegram API, Windows Supervisor и Docker Compose topology не меняются.

### Проверки

Проверяются shell syntax, project notes contract, unit tests, type check и Docker build. Финальный production smoke выполняется обновлением через Telegram после merge.

### PR и commit

Ветка `agent/server-supervisor-docker-config-hotfix`. PR создаётся после публикации изменений.

### Незавершённое

После merge один раз применить environment-переменные к установленному systemd unit и повторить Telegram update с `2e7250e5` на актуальный `main`.

### Следующий шаг

Дождаться зелёного CI, слить hotfix, применить unit environment на VPS и подтвердить успешный deploy, healthcheck и неизменный `StartedAt` PostgreSQL/Hermes.
