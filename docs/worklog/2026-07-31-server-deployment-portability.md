# 2026-07-31 — Server deployment portability

- Дата: 2026-07-31
- ID: server-deployment-portability
- Линия/фаза: hotfix/эксплуатация вне фаз — Linux VPS production migration
- Статус: выполнено
- Ветка: `agent/fix-server-deployment-portability`
- Базовый commit: `55ef763d5783073b5fc732e87262667dbb23a6e2`
- PR: #485

## Перед началом

### Цель

Устранить deployment-blockers, обнаруженные при реальном переносе Velvet с Windows на Ubuntu VPS, не ослабляя защиту миграций и не включая платные AI-функции.

### Исходный контекст

Production dump был создан PostgreSQL 17.6, серверный пример продолжал указывать PostgreSQL 16, Docker build context включал защищённый runtime-каталог `data/postgres`, server smoke ожидал устаревшую таблицу `rp_sessions`, пустой `KIE_USD_TO_RUB` валил bootstrap даже при выключенном Kie, а raw SHA-256 миграций различался между Windows CRLF и Linux LF.

### Планируемый объём

- исключить persistent/runtime data из Docker build context;
- синхронизировать server smoke с канонической RP-схемой;
- закрепить PostgreSQL 17 и безопасные disabled defaults в server env example;
- нормализовать line endings только для checksum SQL-миграций, сохранив блокировку реальных изменений;
- добавить regression-тесты для всех обнаруженных deployment-contract дефектов.

### Критерии готовности

- обычный Docker build не читает PostgreSQL volume;
- `scripts/server_smoke.py` проходит без runtime monkeypatch;
- выключенный Kie принимает пустые числовые env values, а включённый по-прежнему требует положительный курс;
- CRLF/LF версии одного SQL принимаются как одна миграция, изменённый SQL отклоняется;
- Docker build, type check, tests, restore drill и project notes contract проходят в CI.

### Риски и ограничения

Платные provider smoke-tests не входят в PR. Kie и GRS остаются выключенными до отдельной проверки цен и минимальных live-генераций. Byesu и Hermes не включаются без доступных моделей и оплаченного provider account.

### Стабилизационное обоснование

Изменение не добавляет предметный функционал и не меняет пользовательский Telegram flow. Оно стабилизирует существующий server deployment, restore и migration verification contracts.

## После завершения

Статус: выполнено.

### Фактически сделано

- `.dockerignore` исключает PostgreSQL, backups, logs, runtime, Hermes и legacy `server-data` из build context.
- `.env.server.example` закреплён на `postgres:17-alpine`; `KIE_USD_TO_RUB=0` безопасен для выключенного провайдера.
- Server smoke проверяет `roleplay_sessions`.
- Kie numeric parser применяет документированные defaults к пустым значениям, сохраняя строгую enabled-валидацию.
- Migration checksum канонизируется по LF, принимает исторические raw LF/CRLF hashes и переписывает legacy hash в canonical без повторного запуска SQL.
- Добавлен отдельный regression suite `tests/test_server_deployment_portability.py`.

### Изменённые модули и контракты

- `.dockerignore` — build-context boundary;
- `.env.server.example` — production image/defaults contract;
- `scripts/server_smoke.py` — post-deploy schema smoke;
- `velvet_bot/core/config/kie.py` — disabled numeric configuration parsing;
- `velvet_bot/database.py` — portable migration checksum verification;
- `tests/test_server_deployment_portability.py` — regression coverage.

### Миграции и совместимость

SQL-файлы миграций не изменялись. Канонический checksum строится после преобразования CRLF/CR в LF. Исторические LF/CRLF hashes принимаются только при полном совпадении SQL после нормализации line endings; любое иное изменение остаётся фатальной ошибкой.

### Проверки

- GitHub Actions `type check` — успешно;
- GitHub Actions `docker build` — успешно;
- GitHub Actions `tests`, `backup restore drill` и повторный `project notes contract` — выполняются на актуальном head PR #485.

### PR и commit

Draft PR #485: `agent/fix-server-deployment-portability` → `main`.

### Незавершённое

После зелёного CI необходимо слить PR, обновить VPS, выполнить обычный Docker build без `git archive`, запустить штатный `scripts/server_smoke.py` и только затем провести минимальные платные smoke-tests Kie/GRS.

### Следующий шаг

Дождаться зелёного CI, слить PR #485 и обновить `/srv/velvet` с повторной проверкой Compose, logs и server smoke.