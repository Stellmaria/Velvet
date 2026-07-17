# Текущий статус разработки Velvet

Дата актуализации: 17 июля 2026 года.

Текущая стабильная версия: `1.3.0`.

## Назначение

Velvet Archive — owner-oriented архивный Telegram-бот. Его домены: персонажи, истории, медиа, референсы, публикации, аналитика, AI-проверки и эксплуатация владельцем.

Аукционный бот является отдельным продуктом. Его ставки, лоты, колоды, валюты и режимы торгов в Velvet Archive не входят.

## Режим стабилизации

Приоритет определяется `docs/stabilization_policy.md`:

- стабилизировать и упростить существующий функционал;
- улучшать скорость, надёжность, контроль и читаемость;
- добавлять новый код только как улучшение существующего сценария;
- не расширять предметную область без отдельного плана после стабилизации.

## Существующий функционал

- архив персонажей, историй, медиа и референсов;
- категории, вселенные и несколько историй;
- публичный архив, лайки, подписки и уведомления;
- preview и оригиналы изображений;
- промты, медиасеты и визуальные дубли;
- аналитика канала и обсуждений;
- импорт истории Telegram;
- проверка, расписание и отправка публикаций;
- backup и restore drill;
- WorkerManager, диагностика и центр ошибок;
- Velvet AI;
- Supervisor, Codex workflow и безопасная удалённая консоль.

## Production foundation

Завершены:

- Python 3.13 и PostgreSQL 16;
- Dockerfile и Docker Compose;
- container healthcheck и Docker CI;
- автоматический restore drill;
- release workflow;
- production checklist;
- стабильный релиз `1.3.0`.

## Архитектурная очистка P1

Фазы 12–17 завершены:

- SQL удалён из части handlers;
- publication operations используют `PublicationActions`;
- analytics management и owner forms разделены;
- multi-story использует domain repositories;
- runtime monkeypatch удалён;
- compatibility installers превращены в безопасные фасады/no-op;
- добавлены архитектурные regression-тесты.

## Фаза 18: публичная PostgreSQL-граница

Статус: срезы 18A–18P реализованы, работа продолжается.

Переведены на `Database.acquire()`:

- character и story repositories;
- archive и public archive;
- reference;
- media quality;
- publication repository;
- полный discussion-контур;
- archive preview;
- publication validation;
- publication draft.

Контракты сохранены:

- inbox upsert и выбор source items;
- создание draft/items/event в одной транзакции;
- owner scope и status guards;
- spoiler, text, schedule, cancel и retry semantics;
- SQL, параметры и mapping domain-моделей.

Private pool inventory:

- исходно: 130 обращений в 35 production-файлах;
- после 18N: 128 в 34 файлах;
- после 18O: 126 в 33 файлах;
- после 18P: 118 в 32 файлах;
- явные domain repositories из baseline закрыты;
- baseline контролируется AST-тестом и SHA-256 identity методов;
- новые неучтённые обращения блокируются CI.

Следующий срез: **18Q, `SystemRepository`**, 2 connection points. Ожидаемый baseline: 116 обращений в 31 файле.

## Фаза 19: Velvet AI

Статус: завершена.

- единое меню качества;
- журнал AI-заданий;
- lifecycle `pending/processing/ready/error/interrupted`;
- проверка изображения, референса, промта, палитры, оформления и медиасета;
- PostgreSQL integration tests и callback contracts;
- callbacks медиасетов подтверждаются до долгих операций.

## Фаза 20: Supervisor

Статус кода: завершён.

Реализованы:

- безопасная удалённая консоль;
- self-restart/self-update через внешний Windows bootstrap;
- fast-forward update, tests, rollback, lock и healthcheck;
- Telegram-отчёт операции.

Не подтверждено живой эксплуатацией:

1. self-restart на целевой Windows;
2. update-and-restart;
3. success/error Telegram report после bootstrap.

## Документация и контроль

- `docs/project_memory.md` — долгосрочная карта;
- `docs/development_status.md` — текущий статус;
- `docs/stabilization_policy.md` — допустимый новый код и ворота;
- `docs/private_pool_inventory.*` — измеримый PostgreSQL-долг;
- `docs/worklog/` — дневники до/после работы;
- `AGENTS.md` — обязательные правила;
- `CHANGELOG.md` — заметные изменения;
- CI блокирует PR без завершённого worklog.

## Текущий P2-план

1. Фаза 18Q: `SystemRepository`.
2. Repository-классы AI/quality/error/report отдельными срезами.
3. Вынести DB access из handlers в application/domain services.
4. Аудит долгих callback-сценариев.
5. Сократить широкие `except Exception`.
6. Создать staging-бота и staging-базу.
7. Провести независимый backup/restore drill.
8. Добавить encrypted offsite backup.
9. Добавить AI duration/error/cost metrics.

## Правила дальнейшей разработки

- новый код обязан улучшать существующую функцию;
- handler не получает SQL;
- business operation создаётся через use case/domain service;
- private pool срез уменьшает baseline, а не переносит долг;
- старая применённая миграция не редактируется;
- инфраструктура считается production-ready только после доступной живой проверки;
- каждая работа имеет worklog, CI, PR/commit и следующий шаг.
