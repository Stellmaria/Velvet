# 2026-07-31 — Права доступа Hermes Coder preflight

- Дата: `2026-07-31`
- ID: `hermes-preflight-data-permissions`
- Линия/фаза: `server operations`
- Статус: `завершено`
- Ветка: `fix/hermes-preflight-data-permissions`

## Перед началом

### Цель

Исправить отказ preflight из-за недоступного `config.yaml` при запуске от systemd-пользователя `velvet`.

### Исходный контекст

После успешного заполнения всех model, Telegram и GitHub credentials preflight был запущен командой от пользователя `velvet` и завершился необработанным исключением:

```text
PermissionError: [Errno 13] Permission denied: '/srv/hermes-coders/data/velvet/config.yaml'
```

Installer создавал каталоги `data`, `data/velvet`, `data/max` с владельцем и группой `10000:10000` в режиме `0750`, а `config.yaml` и `SOUL.md` в режиме `0600`. Это подходило процессу Hermes внутри контейнера, но исключало чтение для service user `velvet`, хотя именно он запускает `ExecStartPre` в `hermes-coders.service`.

### Планируемый объём

- сохранить владельца UID `10000` для контейнерного Hermes;
- назначить host-группу `velvet` каталогам и проверяемым metadata-файлам;
- дать группе только чтение и traversal без записи;
- исправлять права и на уже существующей установке при повторном installer;
- преобразовать `PermissionError` в понятный `PreflightError`;
- добавить regression-контракт.

### Критерии готовности

- `velvet` может читать `config.yaml` и `SOUL.md` обоих coder;
- UID `10000` остаётся владельцем данных;
- secret env остаются `0600` и не становятся group-readable;
- runtime state Hermes не открывается целиком группе;
- systemd preflight проходит без запуска gateway;
- ошибки прав выводятся одной диагностической строкой без traceback.

## После завершения

### Фактически сделано

Installer теперь создаёт data-каталоги как `10000:velvet` с режимом `0750`. Проверяемые `config.yaml`, `SOUL.md` и `.gitconfig` получают владельца `10000`, группу `velvet` и режим `0640`. Повторный installer принудительно исправляет права уже существующих файлов, поэтому production bootstrap можно продолжить без удаления workspaces, secrets или образов.

Preflight получил helper `require_readable_file`, который переводит `PermissionError` в понятное сообщение о владельце, группе и режиме вместо Python traceback.

### Безопасность

- Telegram, GitHub, model и DB env остаются `0600` под владельцем `velvet`;
- группа получает только чтение metadata-файлов без API keys;
- каталоги остаются закрыты для остальных пользователей;
- контейнерный Hermes сохраняет полный доступ как владелец UID `10000`.

### Проверки

Regression-контракт проверяет:

- группу `$APP_GROUP` на data-каталогах;
- режим `0640` для metadata;
- исправление владельца и группы существующих файлов;
- обработку `PermissionError` без traceback;
- существующие Bash, Python, Compose и изоляционные контракты.

### Незавершённое

После merge требуется обновить `/srv/velvet`, повторно выполнить installer для исправления прав, затем повторить preflight. Только после результата `Hermes Coder preflight: OK` разрешается включить `hermes-coders.service`.
