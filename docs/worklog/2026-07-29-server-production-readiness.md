# 2026-07-29 — подготовка production-переноса на Linux VPS

- Дата: 2026-07-29
- Обновлено: 2026-07-30
- ID: server-production-readiness
- Линия/фаза: Линия C — deployment / production migration
- Статус: `завершено в коде, ожидает живого VPS deployment`
- Ветка: `agent/server-production-readiness`
- Актуальная база: `main` после PR #391

## Цель

Подготовить воспроизводимый и проверяемый серверный контур Velvet для Linux VPS: отдельный production Compose, безопасный env-шаблон, preflight до запуска, полный restore drill дампа, smoke-проверку после старта и systemd-автозапуск без ручного импровизированного администрирования.

## Исходный контекст

В `main` уже доступны Kie/GRS media generation, PostgreSQL lifecycle AI-задач, budget guard, Flash → Pro → sensitive VL, подтверждаемые VL-партии, облачный RP, Telegram Storage, Supervisor и ограниченная Hermes-эскалация. Локальный `docker-compose.yml` не отделяет Windows/dev-контур от production, а старый deploy-скрипт не проверяет финальный dump полным восстановлением до изменения кода.

Серверный PR был первоначально создан от старого `main` и к 30 июля отстал на 155 коммитов. Ветка пересобрана поверх актуального `main`, чтобы сохранить чистый deployment-only diff и не протащить устаревшие варианты Kie, GRS, Wan и Grok.

## Фактически сделано

- добавлен отдельный `docker-compose.server.yml`;
- PostgreSQL не публикуется наружу и хранится в server data directory;
- bot запускается без публичного порта, с healthcheck, лимитами ресурсов, dropped capabilities и `no-new-privileges`;
- Hermes остаётся optional profile и не получает Docker socket, production `.env`, PostgreSQL volume или рабочий каталог бота;
- добавлен `.env.server.example` с актуальными RP, VL, Kie, GRS, Grok 1.5, Seedance 1.5 Pro, Wan 2.7 и НБРБ-настройками;
- первый boot фиксирован с AI, Kie, Hermes, Codex и Krita, выключенными;
- добавлен `scripts/server_preflight.py`, который проверяет placeholders, секреты, права env, PostgreSQL host, feature flags, pricing и разделение Telegram tokens;
- deploy script создаёт custom-format pre-deploy dump и полностью восстанавливает его в disposable PostgreSQL DB до изменения кода;
- добавлен `deploy/server/verify-dump.sh` с безопасным префиксом временной базы и forced cleanup;
- добавлен `scripts/server_smoke.py` для PostgreSQL, миграций, критичных таблиц, backup directory и optional Telegram `getMe`;
- добавлен systemd unit для автоматического запуска Compose после Docker/network;
- добавлены Docker host hardening notes и daemon logging example;
- написан полный `docs/SERVER_PRODUCTION_RUNBOOK.md` с первым запуском, dump/restore, smoke, rollback и поэтапным включением платных функций;
- добавлены unit и deployment contract tests.

## Безопасность первого запуска

Первый boot выполняется с:

```env
AI_TEXT_ENABLED=false
AI_VISION_ENABLED=false
AI_VISION_QUEUE_ENABLED=false
KIE_ENABLED=false
HERMES_INCIDENT_ENABLED=false
CODEX_ENABLED=false
KRITA_WATERMARK_ENABLED=false
```

Каждый платный или агентный контур включается отдельно после повторного preflight и соответствующего live smoke-test.

## Миграции и совместимость

Этот срез не добавляет миграции PostgreSQL. Deployment-файлы используют текущий набор миграций `main` и сохраняют локальный Windows/dev Compose до фактического переключения production.

Второй Telegram-бот намеренно не добавлен фиктивным service. Для него по-прежнему нужны реальный repository, start command, token, env contract, database choice, migrations, healthcheck и backup policy.

Krita остаётся выключенной на Linux VPS до появления отдельного удалённого worker или замены серверной библиотекой.

## Проверки

До merge обязательны:

- server preflight tests;
- Compose/systemd/deploy shell contracts;
- server smoke tests;
- полный tests workflow;
- type check;
- Docker build;
- project notes contract;
- backup restore drill.

Живые VPS, SSH, Telegram token, provider API keys и Hermes model в CI отсутствуют. Их проверка выполняется только по runbook после merge.

## Незавершённое вне кода

- приобрести или подготовить VPS Ubuntu 24.04 LTS;
- установить Docker/Compose и настроить SSH/firewall;
- создать `.env.server` и `.env.hermes` с правами `600`;
- сделать финальный Windows PostgreSQL dump;
- выполнить restore drill и восстановление на VPS;
- запустить базовый бот без платных функций;
- выполнить server smoke;
- по очереди включить GRS/Kie, RP, VL queue и Hermes;
- проверить Telegram Storage backfill и encrypted backup;
- после периода стабильности отключить Windows-контур.

## Следующий шаг

После зелёного CI слить PR и начать живой deployment строго с production preflight, проверенного финального dump и первого запуска без AI/Kie/Hermes.
