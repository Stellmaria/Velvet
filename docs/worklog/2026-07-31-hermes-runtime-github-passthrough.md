# 2026-07-31 — Runtime passthrough GitHub token для Hermes Coder

- Дата: `2026-07-31`
- ID: `hermes-runtime-github-passthrough`
- Линия/фаза: `server operations`
- Статус: `завершено`
- Ветка: `fix/hermes-runtime-gh-token-passthrough`
- Базовый commit: `8827cce21e3448155e2af0b128b46f5e15affe5f`

## Перед началом

### Цель

Сделать `GH_TOKEN` доступным именно дочерним terminal-процессам Hermes Coder, не раскрывая model, Telegram или database credentials.

### Исходный контекст

Оба coder-контейнера содержали корректные отдельные fine-grained GitHub tokens. Прямая проверка внутри контейнеров подтвердила:

```text
container GH_TOKEN: SET
token type: fine-grained
TERMINAL_ENV_PASSTHROUGH: ["GH_TOKEN"]
AUTH_OK login=Stellmaria
```

При этом команды, запущенные самим Hermes через Telegram, продолжали получать:

```text
You are not logged into any GitHub hosts.
```

Одновременно runtime-конфигурации обоих coder показали:

```text
env_passthrough: GH_TOKEN MISSING
```

Причина: upstream Hermes поддерживает allowlist через `terminal.env_passthrough` в `config.yaml`. Переменная `TERMINAL_ENV_PASSTHROUGH`, ранее добавленная в Compose как предполагаемый override, не входит в документированный environment contract закреплённой версии и не изменяла runtime config. Канонический config уже содержал правильное поле, но installer намеренно не перезаписывал существующие runtime configs после миграции schema 33.

### Планируемый объём

- удалить неподдерживаемый Compose override;
- добавить узкую идемпотентную миграцию только `terminal.env_passthrough -> GH_TOKEN`;
- запускать миграцию перед каждым preflight;
- проверять результат в preflight;
- сохранять существующие runtime настройки, права и model routing;
- не добавлять в passthrough provider, Telegram или DB secrets;
- добавить unit и contract regression tests.

### Критерии готовности

- runtime config обоих coder содержит `GH_TOKEN` в `terminal.env_passthrough`;
- повторный запуск миграции не создаёт дубликаты;
- существующие passthrough-переменные сохраняются;
- preflight блокирует запуск при отсутствии allowlist;
- `gh auth status` и `gh repo view` работают из Telegram terminal;
- secret env остаются `0600`;
- CI checks проходят.

### Риски и ограничения

Terminal-команды coder получают доступ к отдельному fine-grained GitHub token своего контейнера. Это необходимая возможность для Git, issues и pull requests. Токены ограничены одним репозиторием и минимальными permissions. Миграция меняет только имя разрешённой переменной в runtime YAML и не читает значение токена.

## После завершения

### Фактически сделано

Добавлен `deploy/hermes-coders/ensure_runtime_config.py`. Скрипт:

- находит top-level `terminal` section;
- поддерживает block и inline `env_passthrough`;
- сохраняет существующие entries;
- добавляет только `GH_TOKEN`;
- работает идемпотентно;
- сохраняет mode файла;
- отказывается менять неизвестный scalar-формат вместо рискованного повреждения YAML.

Systemd теперь выполняет patcher с root-read/write перед Python preflight. Docker Compose `config`, `up`, `stop` и `reload` по-прежнему работают от пользователя `velvet`.

Preflight импортирует тот же parser и блокирует запуск, если runtime config не разрешает `GH_TOKEN`.

Неподдерживаемый `TERMINAL_ENV_PASSTHROUGH` удалён из Compose, чтобы конфигурация больше не создавала ложного ощущения безопасности.

Installer и README обновлены для уже существующих runtime configs.

### Миграции и совместимость

SQL-миграций нет. Production Velvet, Max, PostgreSQL, Hermes Operator, workspaces, sessions, home channels, model keys, Telegram tokens и read-only DB roles не меняются. Для применения требуется обновить checkout, установить новый systemd unit и перезапустить `hermes-coders.service`.

### Проверки

Добавлены unit tests для:

- вставки allowlist в существующий `terminal` section;
- сохранения существующих entries;
- идемпотентности;
- inline empty list;
- отсутствующего terminal section;
- сохранения file mode;
- отказа на неизвестном scalar-формате.

Contract tests проверяют порядок:

```text
runtime patch -> preflight -> compose config -> compose up
```

Также проверяются отсутствие неподдерживаемого env override и отсутствие model/Telegram secrets в patcher.

### Незавершённое

После merge требуется обновить `/srv/velvet`, установить обновлённый unit, выполнить `daemon-reload`, перезапустить coder-сервис и повторить Telegram read-only GitHub smoke test.

### Следующий шаг

Дождаться зелёных CI checks, слить PR, применить unit на VPS и подтвердить `gh auth status` у Velvet и Max Coder.
