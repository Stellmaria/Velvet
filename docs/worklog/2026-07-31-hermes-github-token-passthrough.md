# 2026-07-31 — GitHub token passthrough для Hermes Coder

- Дата: `2026-07-31`
- ID: `hermes-github-token-passthrough`
- Линия/фаза: `server operations`
- Статус: `завершено`
- Ветка: `fix/hermes-coder-github-token-passthrough`
- Базовый commit: `07138a89fc2b2ae82a5a1ef9f500a041a102f4b5`

## Перед началом

### Цель

Разрешить терминальным командам изолированных Hermes Coder использовать отдельные fine-grained GitHub tokens без раскрытия provider, Telegram или database credentials.

### Исходный контекст

Оба coder-контейнера успешно прошли preflight, подключились к Telegram, подтвердили модели mini, terra и luna, правильные workspaces и read-only PostgreSQL identities. При этом команды из Telegram:

```text
gh auth status
gh repo view ...
```

сообщили, что GitHub CLI не авторизован, хотя `GH_TOKEN` был заполнен в отдельном env-файле каждого контейнера и прошёл preflight.

Hermes Agent намеренно очищает чувствительные переменные из окружения дочерних terminal и execute_code процессов. Переменные с `TOKEN` в имени доступны агентским командам только через явный `terminal.env_passthrough`. Это защитный механизм upstream, а не ошибка Docker Compose или введённых токенов.

### Планируемый объём

- разрешить только `GH_TOKEN` в terminal и execute_code дочерних процессах;
- не передавать model keys, Telegram token, database password или иные secrets;
- сохранить отдельный GH token для Velvet и Max через существующие env-файлы;
- обеспечить применение настройки к уже созданным runtime configs через environment override;
- добавить regression-контракт;
- не менять production Velvet, Max, PostgreSQL и Hermes Operator.

### Критерии готовности

- `gh auth status` работает из обоих Telegram coder;
- `gh repo view` видит только разрешённый репозиторий;
- `GH_TOKEN` не выводится в логи или ответы;
- provider и Telegram credentials по-прежнему не доступны terminal-процессам;
- оба coder и DB-proxy остаются healthy;
- CI checks проходят.

### Риски и ограничения

Любая команда, которую запускает coder terminal, сможет использовать `GH_TOKEN`. Это осознанно необходимый доступ для Git operations, issues и pull requests. Риск ограничен отдельными fine-grained tokens, привязанными к одному репозиторию и минимальным permissions. Model keys, Telegram token и DB credentials не добавляются в passthrough.

## После завершения

### Фактически сделано

В каноническом `deploy/hermes-coders/config.yaml` добавлен:

```yaml
terminal:
  env_passthrough:
    - GH_TOKEN
```

В Compose anchor coder-сервисов добавлен environment override:

```yaml
TERMINAL_ENV_PASSTHROUGH: '["GH_TOKEN"]'
```

Override нужен для уже существующих `/srv/hermes-coders/data/*/config.yaml`, которые Hermes мигрировал до schema 33 и которые installer намеренно не перезаписывает. После пересоздания coder-контейнеров настройка применяется без изменения сохранённых сессий, home channel и model routing.

### Миграции и совместимость

SQL-миграций нет. Secret env, workspaces, read-only DB roles, Docker networks и volumes не меняются. Требуется только обновление Compose и пересоздание двух coder-контейнеров. DB-proxy могут остаться без изменений, хотя `docker compose up -d` безопасно сверит весь project.

### Проверки

Regression-контракт проверяет:

- наличие `GH_TOKEN` в каноническом `terminal.env_passthrough`;
- наличие `TERMINAL_ENV_PASSTHROUGH` в Compose;
- отсутствие model и Telegram tokens в passthrough;
- сохранение существующих изоляционных, network, build и preflight контрактов.

### PR и commit

- Ветка: `fix/hermes-coder-github-token-passthrough`
- Основные commits: `256f82d19c83bc7e9a77dbb289f19a3bb38a101c`, `db920198890aee785812a0798aa577a91a92abc2`, `4fd1afb5022a28f1299e673c889e334cefd81376`

### Незавершённое

После merge требуется обновить server checkout и выполнить `systemctl restart hermes-coders.service`, затем повторить read-only `gh auth status` и `gh repo view` в обоих Telegram coder.

### Следующий шаг

Дождаться зелёных CI checks, слить PR, обновить `/srv/velvet`, пересоздать coder-контейнеры и подтвердить GitHub auth без вывода токенов.
