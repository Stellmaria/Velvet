# 2026-07-31 — Hermes preflight после runtime rewrite

- Дата: `2026-07-31`
- ID: `hermes-preflight-runtime-rewrite`
- Линия/фаза: `server operations`
- Статус: `завершено`
- Ветка: `fix/hermes-preflight-root-read`
- Базовый commit: `c72eba4e2e1aae2fad07d3d856725202a719c744`

## Перед началом

### Цель

Сделать перезапуск `hermes-coders.service` устойчивым к тому, что Hermes Agent атомарно переписывает runtime `config.yaml` под UID контейнера.

### Исходный контекст

После первого успешного запуска оба coder работали около 33 минут. При следующем `systemctl restart` systemd сначала остановил контейнеры, затем `ExecStartPre` от пользователя `velvet` не смог прочитать:

```text
/srv/hermes-coders/data/velvet/config.yaml
```

Предыдущий installer выставлял group-readable режим, но Hermes при миграции runtime schema переписал файл под UID/GID контейнера. Из-за этого исправление прав installer не переживало следующий runtime rewrite.

### Планируемый объём

- оставить Docker Compose и gateway под непривилегированным пользователем `velvet`;
- дать повышенное чтение только процессу preflight;
- не расширять права secret env и runtime data;
- обновить ручную команду preflight и документацию;
- добавить regression-контракт.

### Критерии готовности

- systemd preflight читает runtime metadata независимо от UID/GID после rewrite;
- Compose config, up, stop и reload продолжают выполняться от `velvet`;
- secret env остаются `0600`;
- coder-контейнеры успешно пересоздаются;
- обязательные CI checks проходят.

### Риски и ограничения

Preflight получает root-read только на время проверки. Он не изменяет secrets или runtime files. Знак `+` применяется исключительно к Python preflight command; Docker Compose не получает дополнительных привилегий сверх уже существующего членства пользователя `velvet` в Docker group.

## После завершения

### Фактически сделано

В unit-файле Python preflight запускается с systemd executable prefix `+`:

```ini
ExecStartPre=+/usr/bin/python3 /srv/velvet/deploy/hermes-coders/preflight.py
```

`User=velvet` и `Group=velvet` сохранены. Второй `ExecStartPre`, `ExecStart`, `ExecStop` и `ExecReload` не имеют prefix `+` и продолжают работать от `velvet`.

Installer и README теперь показывают ручной preflight через `sudo env`, а не `sudo -u velvet`, поскольку runtime config после миграции может быть недоступен host-пользователю.

### Миграции и совместимость

SQL-миграций нет. Production Velvet, Max, PostgreSQL, Hermes Operator, workspaces, tokens, model routing и read-only DB roles не меняются. Для применения требуется установить обновлённый unit, выполнить `daemon-reload` и запустить сервис.

### Проверки

Контракт проверяет:

- повышенный prefix только у Python preflight;
- отсутствие prefix у Docker Compose команд;
- сохранение порядка preflight → compose config → compose up;
- обновлённые команды installer и README;
- существующие network, mount, token и model boundaries.

### PR и commit

- Ветка: `fix/hermes-preflight-root-read`
- Основные commits: `db0b11c86f3d608197ab0e5479793e2c4bf1f071`, `bf24915c28e02517e5a01cdeb108c3d59878f625`, `16f31b1871db44eb5fe5d7f11302f6b66632ac37`, `474bed4537a5589c2097e54249bb559f59fdd4a8`

### Незавершённое

После merge требуется обновить `/srv/velvet`, установить новый unit в `/etc/systemd/system`, выполнить `systemctl daemon-reload`, запустить `hermes-coders.service` и повторить GitHub read-only smoke test.

### Следующий шаг

Дождаться зелёного CI, слить PR и восстановить coder-сервис на VPS обновлённым unit-файлом.
