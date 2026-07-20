# Память проекта Velvet

Дата актуализации: 20 июля 2026 года.

Этот файл хранит долгосрочную карту проекта и архитектурные решения. Фактическое состояние продукта находится в `docs/development_status.md`, измеримые inventories — в `docs/private_pool_inventory.*` и `docs/p2_stability_inventory.*`, подробности отдельных работ — в `docs/worklog/`, заметные изменения — в `CHANGELOG.md`.

## Источники истины

Порядок приоритета:

1. код, миграции, тесты и слитые PR;
2. `docs/development_status.md`;
3. машинные architecture/stability inventories;
4. `docs/stabilization_policy.md`;
5. этот документ;
6. worklog и исторические планы.

Старый документ не отменяет фактическое состояние `main`. При расхождении сначала исправляется документ, а не реальность подгоняется под удобный абзац.

## Предметная граница продукта

Velvet Archive — отдельный owner-oriented архивный Telegram-бот для создателя и преимущественно единоличной эксплуатации.

Штатные домены:

- персонажи и истории;
- медиа, референсы и медиасеты;
- публикации;
- аналитика канала и обсуждений;
- AI-проверки;
- backup, Supervisor и эксплуатация владельцем.

Аукционные ставки, лоты, колоды, валюты, победители и режимы торгов относятся к другому продукту и в Velvet Archive не переносятся.

## Режим стабилизации

До закрытия ворот из `docs/stabilization_policy.md` новый код допускается только как улучшение существующего Velvet Archive.

Допустимые цели:

- ускорение и уменьшение количества запросов;
- упрощение архитектуры и интерфейса;
- повышение надёжности и наблюдаемости;
- перенос persistence в repositories/use cases;
- кеши, очереди, batching и фоновые операции для существующих сценариев;
- staging, backup/restore automation, метрики, тесты и документация;
- удаление compatibility-долга и физическое выравнивание структуры.

Новая несвязанная предметная механика откладывается.

# Линия A. Основное развитие текущего Velvet Archive

## Фазы 1–6. Функциональная основа

Статус: завершены.

1. Аналитический центр.
2. Персонажи, алиасы и классификация.
3. Проверка, расписание и отправка публикаций.
4. Качество данных и визуальные дубли.
5. Обсуждения и backup.
6. WorkerManager, диагностика и repository foundation.

## Фаза 7. Модульная архитектура

Статус: основной перенос завершён.

Созданы и используются:

- application layer;
- composition root;
- domain repositories/services;
- infrastructure adapters;
- Telegram presentation root;
- core config и access middleware.

Физический перенос всех старых Telegram controllers и корневых modules в целевые каталоги продолжается отдельной P3-линией и не считается незавершённым бизнес-рефакторингом.

## Фазы 8–11. Управление и production foundation

Статус кода: завершены.

- Фаза 8: Supervisor, restart/update/rollback и Codex workflow;
- Фаза 9: application use cases владельца;
- Фаза 10: access boundaries и центр ошибок;
- Фаза 11: Python 3.13, PostgreSQL 16, Docker, restore drill и release workflow.

Живая Windows-проверка Supervisor остаётся эксплуатационным обязательством.

## Фазы 12–17. Архитектурная очистка P1

Статус: завершены.

- SQL удалён из затронутых handlers;
- добавлен `PublicationActions`/application coordinator;
- разделены analytics management и owner reply-формы;
- multi-story перенесён в domain repositories;
- опасные runtime monkeypatch-мосты удалены;
- compatibility installers сокращены до контролируемых adapters/no-op;
- архитектурные regression-тесты фиксируют закрытые границы.

## Фаза 18. Публичная граница PostgreSQL

Статус: завершена.

Исторические срезы 18A–18AM перенесли character, story, archive, public archive, reference, media quality, publication, discussion, analytics, AI quality, backup, import, error center и media-set persistence на публичные repository boundaries.

Итог:

- исходно: 130 внешних обращений к `Database._require_pool()` в 35 production-файлах;
- сейчас: 0 обращений в 0 production-файлах;
- внутреннее использование внутри `Database` остаётся реализационной деталью;
- новые внешние обращения блокируются CI.

Подробная история находится в worklog и `docs/private_pool_inventory.*`.

## Фаза 19. Velvet AI operations

Статус: завершена.

- полное меню качества;
- постоянный журнал AI-заданий;
- lifecycle `pending/processing/ready/error/interrupted`;
- сравнение с референсом;
- промт против результата;
- палитра и композиция;
- оформление Velvet Anatomy;
- медиасеты;
- callback contracts и PostgreSQL integration tests.

## Фаза 20. Удалённая эксплуатация Supervisor

Статус кода: завершён, живая Windows-проверка обязательна.

- безопасная консоль по allowlist;
- self-restart/self-update через внешний bootstrap;
- fast-forward, tests, rollback, lock и healthcheck;
- Telegram-отчёт операции.

# Линия B. Velvet AI / Qwen

Статус фаз 1–8: завершены.

1. Проверка качества изображения.
2. Сравнение с референсом.
3. Целостность медиасетов.
4. Калибровка.
5. Единый AI-интерфейс.
6. Промт против результата.
7. Палитра и композиция.
8. Оформление Velvet Anatomy.

Дальнейшая AI-работа относится к наблюдаемости, производительности и проверке качества существующих операций, а не к добавлению новой предметной области.

# Линия C. Исторический план раннего рефакторинга

Этот раздел сохранён как compatibility heading для проектного CI. Ранний план фаз 1–11 находится в `docs/development_phases_analytics.md` и не является источником текущего статуса. Аукционные пункты относятся к другому продукту и не используются при выборе задач Velvet Archive.

# Линия D. Стабильность P2

Статус: завершена 19 июля 2026 года.

Итоговый inventory:

- broad exception boundaries: 67;
- approved boundaries: 67;
- unresolved boundaries: 0;
- callback handlers: 97;
- late/missing callbacks: 0;
- следующий срез отсутствует.

Широкие catches сохранены только как проверенные внешние границы с логированием/компенсацией. `asyncio.CancelledError` не поглощается.

# Линия E. Организация структуры P3

Цель: довести физическую структуру пакетов до уже существующих логических границ без массовой переписи работающего бота.

## P3A. Синхронизация источников истины

Статус: выполняется.

- обновить status, memory, архитектурный аудит и changelog после закрытия P2;
- отделить кодовые долги от внешних эксплуатационных проверок;
- не хранить одновременно несколько взаимоисключающих «текущих» планов.

## P3B. Telegram Router bundles

Статус: завершено.

- root router подключает четыре крупные доменные bundles;
- root router не импортирует отдельные `velvet_bot.handlers.*`;
- 57 активных router imports зарегистрированы без дублей;
- порядок регистрации защищается AST-тестом;
- публикации остаются перед архивным catch-all.

## P3C. Физический перенос presentation

Статус: завершено.

Все активные Telegram controllers перенесены в `velvet_bot/presentation/telegram/routers/<domain>/`. В `velvet_bot/handlers` остаются 46 временных module aliases и 0 реализаций. Callback prefixes, команды и use cases при переносе не менялись.

## P3D. Compatibility retirement

Статус: выполняется.

Активные adapters находятся в одном pre-import/post-import реестре. Production legacy-consumer inventory закрыт: 0 production-файлов, 0 references и 0 старых handler modules. Первый compatibility-batch удалил 22 archive/reference aliases, затем отдельный zero-reference срез удалил `ai_jobs` и `quality_calibration`; остаются 44 aliases. Alias-consumer inventory подтверждает, что все 44 оставшихся aliases пока имеют repository references. Удаление продолжается связанными группами после миграции тестов на canonical modules.

## P3E. Repository layout

Статус: открыт.

Нужно постепенно свести исторические варианты:

- `velvet_bot/domains/<domain>/repository.py`;
- `velvet_bot/repositories/`;
- корневые `*_repository.py`.

Правило для нового кода: domain repository либо infrastructure adapter, без создания нового четвёртого размещения.

## P3F. Статическая типизация

Статус: открыт.

Типизация включается постепенно для transport-neutral слоёв. Сначала core/application/domains/services/workers, затем Telegram adapters. Массовое включение strict-mode на весь repository запрещено без baseline и поэтапного плана.

# Открытые обязательства

## На целевой Windows

1. Обновить локальный `main` и перезапустить Velvet Supervisor.
2. Проверить основные owner-, AI- и media-set кнопки на реальном боте.
3. Проверить Supervisor self-restart.
4. Проверить Supervisor update-and-restart.
5. Зафиксировать Telegram success/error report bootstrap.

## Staging и сохранность данных

1. Создать отдельного staging-бота.
2. Создать отдельную staging-базу без доступа к production DSN.
3. Провести независимый backup/restore drill в целевом окружении.
4. Настроить зашифрованную внешнюю репликацию backup.

## Наблюдаемость

1. Добавить метрики длительности AI-задач.
2. Добавить агрегаты ошибок по operation/provider/model.
3. Добавить контролируемые cost units без выдумывания денежной цены там, где provider её не предоставляет.

# Стабилизационные ворота

Закрыты:

- Фаза 18 и private pool debt 0/0;
- новые SQL/DB access из Telegram handlers запрещены;
- P2 broad exception/callback inventory 0 unresolved;
- основные архитектурные документы и worklog framework;
- CI, Docker, backup drill workflow и release foundation.

Не закрыты эксплуатационно:

- живая Windows-проверка Supervisor;
- staging bot/database;
- независимый restore drill на целевой инфраструктуре;
- encrypted offsite backup;
- AI duration/error/cost metrics;
- реальный owner smoke test после обновления.

# Правило выбора следующей задачи

Перед работой агент обязан:

1. определить линию и точный срез;
2. проверить предметную границу;
3. обосновать новый код улучшением существующей функции;
4. прочитать актуальный status, inventory и относящийся worklog;
5. создать стартовую запись до production-кода;
6. определить измеримые критерии готовности;
7. закрыть запись проверками, PR/commit, остатком и следующим шагом.

Работа не считается завершённой, пока итог не записан в проект. Живая проверка, которую CI не способен выполнить, не помечается завершённой по одному факту существования кода.
