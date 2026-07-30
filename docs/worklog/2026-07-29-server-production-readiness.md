# 2026-07-29 — подготовка production-переноса на Linux VPS

- Дата: 2026-07-29
- ID: server-production-readiness
- Линия/фаза: Линия C — deployment / production migration
- Статус: `частично`
- Ветка: `agent/server-production-readiness`
- Базовый commit: `1ef6cb2928518719d9ebfa07d6c486b3a686f484`

## Перед началом

### Цель

Подготовить воспроизводимый и проверяемый серверный контур Velvet для Linux VPS: отдельный production Compose, безопасный env-шаблон, preflight до запуска, полный restore drill дампа, smoke-проверку после старта и systemd-автозапуск без ручного импровизированного администрирования.

### Исходный контекст

В `main` уже доступны Kie/GRS media generation, PostgreSQL lifecycle AI-задач, budget guard, Flash → Pro → sensitive VL, подтверждаемые VL-партии, облачный RP, Telegram Storage, Supervisor и ограниченная Hermes-эскалация. Локальный `docker-compose.yml` не отделяет Windows/dev-контур от production, а старый deploy-скрипт не проверяет финальный dump полным восстановлением до изменения кода.

Серверный PR первоначально был создан от старого `main` и к 30 июля отстал на 155 коммитов. Ветка пересобрана поверх актуального `main`, чтобы сохранить чистый deployment-only diff и не протащить устаревшие варианты Kie, GRS, Wan и Grok.

### Планируемый объём

- добавить отдельный `docker-compose.server.yml` без публичного PostgreSQL;
- добавить `.env.server.example` с безопасным первым запуском;
- добавить server preflight без вывода секретов;
- проверять placeholders, права env, Docker/Compose, DB URL и feature flags;
- добавить restore drill в одноразовую PostgreSQL DB;
- добавить read-only smoke-проверку БД, миграций, backup directory и Telegram `getMe`;
- добавить systemd unit;
- написать точный runbook первого запуска, rollback и поэтапного включения AI;
- добавить unit и deployment contract tests;
- сохранить второй бот за пределами Compose до получения его реального контракта.

### Критерии готовности

- production Compose не публикует PostgreSQL и не передаёт Docker socket Hermes;
- первый запуск возможен с AI, Kie, Hermes, Codex и Krita, выключенными;
- preflight блокирует placeholders, слабые секреты и опасные сочетания флагов;
- preflight не выводит токены и пароли;
- restore drill создаёт только одноразовую DB с безопасным префиксом и удаляет её;
- smoke подтверждает доступность БД, миграций и критичных таблиц;
- systemd корректно поднимает и останавливает Compose;
- runbook содержит перенос, smoke, rollback и сохранение локального контура;
- tests, type check, Docker build, notes contract и backup restore drill проходят.

### Риски и ограничения

- реальные VPS, SSH, Telegram token и provider API keys отсутствуют в CI;
- Hermes image и model ID требуют отдельной живой проверки;
- второй Telegram-бот нельзя корректно добавить без repository, command, env и DB contract;
- внешний uptime-monitor и публичный HTTPS health endpoint остаются отдельным сетевым этапом;
- Krita остаётся выключенной на Linux до отдельного удалённого worker или серверной замены;
- production secrets не коммитятся.

## После завершения

### Фактически сделано

- добавлен отдельный `docker-compose.server.yml`;
- PostgreSQL не публикуется наружу и хранится в server data directory;
- bot запускается без публичного порта, с healthcheck, resource limits, dropped capabilities и `no-new-privileges`;
- Hermes остаётся optional profile и не получает Docker socket, production `.env`, PostgreSQL volume или рабочий каталог бота;
- добавлен `.env.server.example` с актуальными RP, VL, Kie, GRS, Grok 1.5, Seedance 1.5 Pro, Wan 2.7 и НБРБ-настройками;
- первый boot фиксирован с AI, Kie, Hermes, Codex и Krita, выключенными;
- добавлен `scripts/server_preflight.py`;
- deploy script создаёт custom-format pre-deploy dump и полностью восстанавливает его в disposable DB до изменения кода;
- добавлен `deploy/server/verify-dump.sh` с forced cleanup;
- добавлен `scripts/server_smoke.py`;
- добавлен systemd unit;
- добавлены Docker host hardening notes и daemon logging example;
- написан `docs/SERVER_PRODUCTION_RUNBOOK.md`;
- добавлены unit и deployment contract tests;
- ветка пересобрана одним deployment-коммитом поверх актуального `main`.

### Миграции и совместимость

Новые миграции PostgreSQL не добавляются. Deployment использует текущий набор миграций `main` и сохраняет локальный Windows/dev Compose до фактического переключения production.

Второй Telegram-бот намеренно не добавлен фиктивным service. Для него нужны реальный repository, start command, token, env contract, database choice, migrations, healthcheck и backup policy.

Legacy Kie-переменные остаются в server env как deployment bridge для уже существующих конфигураций и queued-task compatibility.

### Проверки

До merge выполняются:

- server preflight tests;
- Compose/systemd/deploy shell contracts;
- server smoke tests;
- полный tests workflow;
- type check;
- Docker build;
- project notes contract;
- backup restore drill.

Live VPS, provider API и Telegram smoke выполняются только после merge по runbook.

### PR и commit

- PR: `#359` — «Подготовить production-перенос Velvet на Linux VPS»;
- ветка: `agent/server-production-readiness`;
- ветка пересобрана от актуального `main` 30 июля 2026 года;
- проверяемый head обновляется по результатам CI.

### Незавершённое

- получить полностью зелёный CI после пересборки ветки;
- снять draft и слить PR #359;
- подготовить VPS Ubuntu 24.04 LTS;
- создать `.env.server` и `.env.hermes` с правами `600`;
- сделать финальный Windows PostgreSQL dump;
- выполнить restore drill и восстановление на VPS;
- запустить базовый бот без платных функций;
- по очереди включить GRS/Kie, RP, VL queue и Hermes;
- проверить Telegram Storage backfill и encrypted backup;
- после периода стабильности отключить Windows-контур.

### Следующий шаг

Исправить результаты CI после пересборки ветки, получить зелёные проверки, снять draft и слить PR. Затем начать живой deployment с production preflight, проверенного финального dump и первого запуска без AI/Kie/Hermes.
