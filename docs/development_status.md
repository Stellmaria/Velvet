# Текущий статус разработки Velvet

Дата актуализации: 20 июля 2026 года.

Текущая стабильная версия: `1.3.0`.

## Назначение

Velvet Archive — owner-oriented архивный Telegram-бот. Его домены: персонажи, истории, медиа, референсы, публикации, аналитика, AI-проверки и эксплуатация владельцем.

Аукционный бот является отдельным продуктом. Ставки, лоты, колоды, валюты и режимы торгов в Velvet Archive не входят.

## Режим стабилизации

Приоритет определяется `docs/stabilization_policy.md`:

- стабилизировать и упрощать существующий функционал;
- улучшать скорость, надёжность, контроль и читаемость;
- новый код добавлять только как улучшение существующего сценария;
- не расширять предметную область до закрытия эксплуатационных ворот.

## Существующий функционал

Работают:

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

Завершены в коде и CI:

- Python 3.13 и PostgreSQL 16;
- Dockerfile и Docker Compose;
- container healthcheck и Docker CI;
- автоматический restore drill;
- release workflow;
- production checklist;
- стабильный релиз `1.3.0`.

## Архитектурный статус

### Фазы 1–6: функциональная основа

Статус: завершены.

### Фаза 7: модульная архитектура

Статус: основной перенос завершён.

- `main.py` является короткой точкой входа;
- composition root и lifecycle находятся в `velvet_bot/app`;
- application/use-case слой не зависит от aiogram;
- доменные модели, repositories и services введены для основных контуров;
- корневой Telegram Router собирается в `velvet_bot/presentation/telegram`.

### Фазы 8–11: управление и production foundation

Статус: завершены в коде.

Supervisor self-restart/self-update требует живой проверки на целевой Windows и поэтому не считается эксплуатационно подтверждённым.

### Фазы 12–17: архитектурная очистка P1

Статус: завершены.

- SQL удалён из затронутых handlers;
- publication operations используют application coordinator;
- analytics management и owner forms разделены;
- multi-story использует domain repositories;
- опасные runtime monkeypatch-мосты удалены;
- оставшиеся compatibility adapters имеют отдельный контролируемый контур;
- архитектурные regression-тесты блокируют возврат закрытых долгов.

### Фаза 18: публичная PostgreSQL-граница

Статус: завершена.

- исходно: 130 внешних обращений к `Database._require_pool()` в 35 production-файлах;
- сейчас: 0 обращений в 0 production-файлах;
- новые внешние обращения блокируются CI;
- persistence основных доменов использует `Database.acquire()` и repository boundaries.

Источник измерения: `docs/private_pool_inventory.*`.

### Фаза 19: Velvet AI operations

Статус: завершена.

- единое меню качества;
- постоянный журнал AI-заданий;
- lifecycle `pending/processing/ready/error/interrupted`;
- проверка изображения, референса, промта, палитры, оформления и медиасета;
- callback contracts и PostgreSQL integration tests.

### Фаза 20: Supervisor

Статус кода: завершён.

Реализованы безопасная консоль, fast-forward update, tests, rollback, lock, healthcheck, self-restart/self-update bootstrap и Telegram-отчёт операции.

Не подтверждено живой эксплуатацией:

1. self-restart на целевой Windows;
2. update-and-restart;
3. success/error Telegram report после bootstrap.

## Закрытие P2 stability

Статус: завершена 19 июля 2026 года.

Текущий AST-инвентарь:

- broad exception boundaries: 67;
- approved boundaries: 67;
- unresolved boundaries: 0;
- callback handlers: 97;
- late/missing callbacks: 0;
- следующий P2-срез отсутствует.

Источник измерения: `docs/p2_stability_inventory.*`.

Широкие перехваты остались только на проверенных внешних границах подсистем с логированием, компенсацией и явным пробросом отмены.

## P3: организация структуры

Статус: выполняется постепенно без массовой переписи.

### P3A. Источники истины

- синхронизировать `project_memory`, `development_status`, архитектурный аудит и changelog с закрытием P2;
- отделить кодовый долг от внешних эксплуатационных проверок.

### P3B. Telegram composition

Статус: завершено.

- корневой Router подключает четыре крупные доменные bundles;
- 57 активных routers зарегистрированы без дублей;
- порядок catch-all-sensitive routers фиксируется тестом;
- `handlers.router` остаётся только compatibility export без startup side effects.

### P3C. Физический перенос presentation

Статус: завершено.

Все активные Telegram-контроллеры находятся в `velvet_bot/presentation/telegram/routers`. Каталог `velvet_bot/handlers` содержит 68 временных re-export/module aliases и 0 implementations.

### P3D. Compatibility

Статус: выполняется.

Legacy-consumer inventory фиксирует 20 production-файлов, 30 references и 18 старых handler modules после очистки `characters/uncategorized.py` и `stories/management.py`. Новые imports блокируются inventory contract; aliases удаляются небольшими группами после переноса consumers на публичные contracts.

### P3E. Persistence layout

Остаётся постепенно унифицировать расположение repositories между:

- `velvet_bot/domains/<domain>/repository.py`;
- `velvet_bot/repositories/`;
- отдельными историческими `*_repository.py`.

Новые repositories должны появляться в домене либо как инфраструктурный PostgreSQL adapter, а не увеличивать третий вариант размещения.

### P3F. Статическая типизация

Остаётся включать статический анализ постепенно для transport-neutral слоёв: core, application, domains, services и workers. Полное включение strict-mode одним изменением запрещено.

## Эксплуатационные обязательства

Эти пункты не являются незакрытыми кодовыми долгами P2:

1. обновить локальный `main` и перезапустить Supervisor;
2. выполнить smoke test основных owner-, AI- и media-set сценариев на реальном боте;
3. подтвердить Supervisor self-restart и update-and-restart на Windows;
4. создать отдельный staging-бот и staging-базу;
5. провести независимый restore drill в целевом окружении;
6. настроить зашифрованную внешнюю репликацию backup;
7. добавить и проверить метрики длительности, ошибок и стоимости AI-задач.

## Документация и контроль

- `docs/project_memory.md` — долгосрочная карта;
- `docs/development_status.md` — текущий статус;
- `docs/architecture_target.md` — целевая структура;
- `docs/ARCHITECTURE_AUDIT.md` — текущий архитектурный аудит;
- `docs/stabilization_policy.md` — ворота стабилизации;
- `docs/private_pool_inventory.*` — закрытая PostgreSQL-граница;
- `docs/p2_stability_inventory.*` — закрытая stability-линия;
- `docs/legacy_handler_consumer_inventory.*` — измеримый baseline старых handler imports;
- `docs/worklog/` — проверяемая история работ;
- `AGENTS.md` — обязательные правила;
- `CHANGELOG.md` — заметные изменения.

CI блокирует содержательный PR без завершённого worklog.

## Правила дальнейшей разработки

- новый код обязан улучшать существующую функцию;
- handler не получает новый SQL;
- business operation создаётся через use case/domain service;
- новые внешние private pool access запрещены;
- новые broad catches и callback acknowledgment проверяются inventory;
- старая применённая миграция не редактируется;
- инфраструктура считается production-ready только после доступной живой проверки;
- каждая работа имеет worklog, CI, PR/commit, остаток и следующий шаг.
