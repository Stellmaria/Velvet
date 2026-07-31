# 2026-07-31 — Hotfix deploy-lock Server Supervisor

- Дата: `2026-07-31`
- ID: `server-supervisor-deploy-lock-hotfix`
- Линия/фаза: `server operations`
- Статус: `завершено`
- Ветка: `agent/server-supervisor-lock-hotfix`
- Базовый commit: `2e7250e5cea188aa841ff8e5ffab43c619a715eb`

## Перед началом

### Цель

Исправить запуск обновления Velvet из Telegram через Server Supervisor после production smoke-test.

### Исходный контекст

Перезапуск одного контейнера Velvet через Telegram прошёл успешно: `StartedAt` изменился только у `velvet-bot-1`, PostgreSQL и Hermes сохранили прежнее время запуска. Кнопка обновления завершилась ошибкой до fetch и backup: systemd sandbox с `ProtectSystem=strict` запретил запись общего lock-файла `/tmp/velvet-deploy.lock`.

### Планируемый объём

- сохранить единый lock `/tmp/velvet-deploy.lock` для Telegram и ручного SSH deploy;
- разрешить host-side Supervisor запись только в уже используемый `/tmp` дополнительно к `/srv/velvet` и `/srv/velvet/data`;
- не ослаблять остальные ограничения systemd unit;
- закрепить поведение regression-контрактом.

### Критерии готовности

- `deploy/server/deploy.sh` может открыть общий lock из systemd runtime;
- ручной SSH deploy и Telegram update используют один lock;
- `ProtectSystem=strict`, `NoNewPrivileges`, непривилегированный пользователь и отсутствие `PrivateTmp` сохраняются;
- контракт Server Supervisor и обязательный CI проходят.

### Риски и ограничения

`/tmp` становится writable только для процесса Server Supervisor внутри его sandbox. Произвольная консоль по-прежнему отсутствует, а runtime запускает только фиксированные операции. Общий путь lock нужен, чтобы Telegram update и ручной deploy не выполнялись параллельно.

## После завершения

### Фактически сделано

- в `velvet-server-supervisor.service` добавлен `/tmp` в `ReadWritePaths`;
- сохранён общий lock `/tmp/velvet-deploy.lock` без изменения deploy-скрипта;
- добавлен комментарий с причиной исключения в systemd sandbox;
- regression-тест проверяет writable `/tmp` и совпадение пути lock между runtime и SSH.

### Миграции и совместимость

SQL-миграций нет. Docker Compose, PostgreSQL, Telegram callback contract и Windows deprecated Supervisor не меняются. После установки обновлённого unit требуется только `systemctl daemon-reload` и restart Server Supervisor, без reboot VPS.

### Проверки

Добавлен статический contract в `tests/test_server_supervisor_contract.py`. GitHub Actions запускаются на PR hotfix.

### PR и commit

Ветка `agent/server-supervisor-lock-hotfix`; отдельный PR создаётся в `main` после публикации изменений.

### Незавершённое

После merge применить обновлённый systemd unit на production и повторить безопасный no-op update из Telegram.

### Следующий шаг

Дождаться зелёного CI, слить hotfix, обновить unit на VPS и подтвердить успешный статус операции `update`.
