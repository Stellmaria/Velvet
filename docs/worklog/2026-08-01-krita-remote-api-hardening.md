# 2026-08-01 — Защита Krita Remote API

- Дата: `2026-08-01`
- ID: `issue-510-krita-remote-api-hardening`
- Линия/фаза: `P1 security hardening`
- Статус: `завершено`
- Ветка: `fix/issue-510-krita-loopback-security`
- Базовый commit: `42522af0a19d67333e6a0c423af4d6589b201b44`

## Перед началом

### Цель

Закрыть issue #510: сделать optional Krita Remote API fail-closed по сети, аутентификации и загрузке результата.

### Исходный контекст

Runtime по умолчанию слушал `0.0.0.0`, bearer token не имел cooldown, upload проверял только PNG signature и использовал общий staging filename. Compose уже публиковал порт на host loopback, но сам runtime и server preflight не запрещали случайный публичный bind. Исходная ветка PR #537 отстала от `main` и была пересобрана поверх актуальной базы без переноса устаревших generated inventories.

### Планируемый объём

- loopback bind по умолчанию и explicit unsafe override;
- preflight-проверка токена и bind policy;
- cooldown для auth/lease failures без журналирования секретов;
- bounded timeout, размер и параллелизм upload;
- строгая проверка PNG chunks/CRC;
- уникальный staging и гарантированная очистка;
- тесты, документация и синхронизация generated inventories.

### Критерии готовности

- случайный public/wildcard bind блокируется runtime и preflight;
- Docker публикует remote port только на `127.0.0.1`;
- upload принимает только валидный `image/png` с `Content-Length`;
- повторные auth/lease failures получают cooldown;
- токены и имена исходников не попадают в security log;
- compile, preflight, unit tests, mypy, Docker/Krita smoke и project notes зелёные.

### Риски и ограничения

- контейнеру нужен explicit wildcard bind, потому что host-loopback находится вне network namespace контейнера;
- live SSH tunnel и Windows worker smoke остаются эксплуатационной проверкой #411;
- SQL и applied migrations не изменяются.

## После завершения

Статус: `завершено`.

### Фактически сделано

- runtime default изменён на `127.0.0.1`;
- non-loopback bind требует `KRITA_REMOTE_ALLOW_UNSAFE_PUBLIC_BIND=true`;
- Compose явно использует внутренний wildcard только за host-loopback publish;
- server preflight проверяет отдельный token и bind policy;
- health закрывается bearer auth при non-loopback режиме;
- auth/lease failures получают bounded fingerprint-based cooldown;
- upload ограничен по content type, length, size, timeout и concurrency;
- PNG проходит проверку signature, IHDR, dimensions, IDAT, IEND и CRC;
- output/response пишутся через уникальный atomic staging с cleanup;
- same-revision concurrent upload отклоняется;
- добавлены security, deployment и worker protocol regression tests;
- production feature остаётся выключенной по умолчанию.

### Миграции и совместимость

SQL-миграций нет. Windows worker сохраняет тот же HTTP protocol и подключается через SSH tunnel либо другой защищённый gateway. Прямой публичный bind теперь требует явного unsafe override.

### Риски и ограничения

Live SSH tunnel, controlled invalid-token test и Windows worker result upload не выполняются в CI; они остаются частью staging/production acceptance #411.

### Проверки

- compileall и generated inventory checks;
- security/unit contracts Krita Remote API;
- полный tests workflow;
- bounded mypy;
- Docker Compose/build и Krita plugin smoke;
- project notes contract;
- reviewable branch не содержит временных workflow или patch-скриптов.

### PR и commit

- PR: `#537` — `P1: закрыть Krita Remote API по умолчанию`;
- итоговый merge commit заполняется GitHub после слияния.

### Незавершённое

Кодовый scope #510 завершён. Осталась внешняя live acceptance по #411, которая не подменяется зелёным CI.

### Следующий шаг

После merge выполнить отдельный SSH-tunnel/Windows-worker smoke в рамках #411 без открытия публичного порта VPS.