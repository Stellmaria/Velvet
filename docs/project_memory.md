# Память проекта Velvet

Дата актуализации: 21 июля 2026 года.

Этот файл хранит долгосрочную карту проекта и архитектурные решения. Фактическое состояние продукта находится в `docs/development_status.md`, измеримые inventories — в `docs/private_pool_inventory.*`, `docs/p2_stability_inventory.*`, `docs/architecture_layout_inventory.*` и `docs/repository_layout_inventory.*`, подробности отдельных работ — в `docs/worklog/`, заметные изменения — в `CHANGELOG.md`.

## Источники истины

Порядок приоритета:

1. код, migrations, tests и слитые PR;
2. `docs/development_status.md`;
3. generated architecture/stability inventories;
4. `docs/stabilization_policy.md`;
5. этот документ;
6. worklog и исторические планы.

Старый документ не отменяет фактическое состояние `main`. При расхождении исправляется документ, а не реальность подгоняется под удобный абзац.

## Предметная граница продукта

Velvet Archive — отдельный owner-oriented архивный Telegram-бот для создателя и преимущественно единоличной эксплуатации.

Штатные домены:

- персонажи и истории;
- медиа, референсы и медиасеты;
- публикации;
- аналитика канала и обсуждений;
- AI-проверки;
- backup, diagnostics, Supervisor и эксплуатация владельцем.

Аукционные ставки, лоты, колоды, валюты, победители и режимы торгов относятся к другому продукту и в Velvet Archive не переносятся.

## Режим стабилизации

До закрытия ворот из `docs/stabilization_policy.md` новый код допускается только как улучшение существующего Velvet Archive.

Допустимые цели:

- ускорение и уменьшение количества запросов;
- упрощение архитектуры и интерфейса;
- повышение надёжности и наблюдаемости;
- перенос persistence в repositories/use cases;
- кеши, очереди, batching и фоновые операции для существующих сценариев;
- staging, backup/restore automation, метрики, tests и документация;
- удаление compatibility-долга и физическое выравнивание структуры.

Новая несвязанная предметная механика откладывается.

# Линия A. Основное развитие текущего Velvet Archive

## Фазы 1–6. Функциональная основа

Статус: завершены.

1. Аналитический центр.
2. Персонажи, aliases и классификация.
3. Проверка, расписание и отправка публикаций.
4. Качество данных и визуальные дубли.
5. Обсуждения и backup.
6. WorkerManager, diagnostics и repository foundation.

## Фаза 7. Модульная архитектура

Статус: основной логический перенос завершён.

Созданы и используются:

- application layer;
- composition root;
- domain repositories/services;
- infrastructure adapters;
- Telegram presentation root;
- core config и access middleware.

Физическая очистка 110 исторических root modules продолжается отдельными P3-срезами и не считается незавершённым бизнес-рефакторингом.

## Фазы 8–11. Управление и production foundation

Статус кода: завершены.

- Фаза 8: Supervisor, restart/update/rollback и Codex workflow;
- Фаза 9: application use cases владельца;
- Фаза 10: access boundaries и Error Center;
- Фаза 11: Python 3.13, PostgreSQL 16, Docker, restore drill и release workflow.

Живая Windows-проверка Supervisor остаётся эксплуатационным обязательством.

## Фазы 12–17. Архитектурная очистка P1

Статус: завершены.

- SQL удалён из затронутых Telegram controllers;
- добавлен `PublicationActions`/application coordinator;
- разделены analytics management и owner reply-формы;
- multi-story перенесён в domain repositories;
- опасные runtime monkeypatch-мосты удалены;
- архитектурные regression tests фиксируют закрытые границы.

## Фаза 18. Публичная граница PostgreSQL

Статус: завершена.

Исторические срезы 18A–18AM перенесли character, story, archive, public archive, reference, media quality, publication, discussion, analytics, AI quality, backup, import, Error Center и media-set persistence на публичные repository boundaries.

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

## Production diagnostics 2026-07-21

Статус кода: завершено.

- `Velvet Diagnostic Bundle v1` отправляется только владельцу в private chat;
- пакет содержит redacted runtime snapshot, workers, Error Center incidents и log tail;
- critical monitor работает раз в 5 минут с incident cooldown;
- Qwen retry сохраняет `media_ai_profiles.analysis JSONB NOT NULL`;
- permanent oversized/no-preview AI skips логируются как `INFO`, а не как ложные incidents.

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

Этот раздел сохранён как compatibility heading для project CI. Ранний план фаз 1–11 находится в `docs/development_phases_analytics.md` и не является источником текущего статуса. Аукционные пункты относятся к другому продукту и не используются при выборе задач Velvet Archive.

# Линия D. Стабильность P2

Статус: завершена.

Актуальный generated inventory после owner diagnostics:

- broad exception boundaries: 76;
- approved boundaries: 76;
- unresolved boundaries: 0;
- callback handlers: 98;
- late/missing callbacks: 0;
- следующий срез отсутствует.

Широкие catches сохранены только как проверенные внешние границы с логированием/компенсацией. `asyncio.CancelledError` не поглощается.

# Линия E. Организация структуры P3

Цель: довести физическую структуру пакетов до уже существующих логических границ без массовой переписи работающего бота.

## P3A. Синхронизация источников истины

Статус: завершено.

Status, memory, audit, changelog и generated inventories синхронизированы с фактическим `main`. Эксплуатационные проверки не смешиваются с кодовыми архитектурными долгами.

## P3B. Telegram Router bundles

Статус: завершено.

- root Router подключает четыре крупные доменные bundles;
- root Router не импортирует `velvet_bot.handlers.*`;
- 60 активных router imports зарегистрированы без дублей;
- порядок регистрации защищается AST-тестом;
- publication остаётся перед archive catch-all.

## P3C. Физический перенос presentation

Статус: завершено.

Все активные Telegram controllers находятся в `velvet_bot/presentation/telegram/routers/<domain>/`. Legacy handler-файлов, implementations и aliases осталось 0.

## P3D. Compatibility retirement

Статус старого handler compatibility слоя: завершено.

Production legacy-consumer inventory закрыт на 0/0/0, а `velvet_bot.handlers` aliases удалены.

В explicit registry остаются 8 runtime compatibility-компонентов. Каждый должен быть классифицирован как постоянный schema/UI/import-order contract либо удалён вместе с regression-тестом.

## P3E. Repository layout

Статус: завершено.

Repository inventory фиксирует 34 module:

- 33 domain repositories;
- 1 PostgreSQL infrastructure adapter;
- 0 central repositories;
- 0 root repositories.

Пакет `velvet_bot/repositories` удалён. Новый persistence-код создаётся только внутри domain либо reviewed infrastructure boundary.

## P3F. Статическая типизация

Статус: следующий кодовый срез.

Типизация включается постепенно для transport-neutral слоёв. Сначала один ограниченный core/application/domain scope, затем services/workers и только потом Telegram adapters. Массовое включение strict-mode на весь repository запрещено без baseline и поэтапного плана.

# Открытые обязательства

## Кодовые срезы

1. P3F static typing baseline.
2. Классификация 110 исторических root modules.
3. Разбор 8 runtime compatibility components.
4. Duplicate/shared-helper inventory.
5. AI duration/error/provider/model/cost-unit metrics.
6. Heavy Runtime: idle unload, пустой polling, checkpoint/resume.

## На целевой Windows

1. Обновить локальный `main` и перезапустить Velvet Supervisor.
2. Проверить основные owner-, AI-, media-set и diagnostic buttons.
3. Проверить Supervisor self-restart.
4. Проверить Supervisor update-and-restart.
5. Зафиксировать Telegram success/error report bootstrap.

## Staging и сохранность данных

1. Создать отдельного staging-бота.
2. Создать отдельную staging-базу без доступа к production DSN.
3. Провести независимый backup/restore drill в целевом окружении.
4. Настроить зашифрованную внешнюю репликацию backup.

# Стабилизационные ворота

Закрыты:

- Фаза 18 и private pool debt 0/0;
- новые SQL/DB access из Telegram controllers запрещены;
- P2 broad exception/callback inventory 0 unresolved;
- P3 handler compatibility aliases 0;
- P3 repository layout 33 domain + 1 infrastructure, root/central 0;
- CI, Docker, diagnostics, backup drill workflow и release foundation.

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
7. закрыть запись checks, PR/commit, остатком и следующим шагом.

Работа не считается завершённой, пока итог не записан в проект. Живая проверка, которую CI не способен выполнить, не помечается завершённой по одному факту существования кода.
