# Память проекта Velvet

Дата актуализации: 18 июля 2026 года.

Этот файл хранит долгосрочный план и архитектурные решения. Фактическое состояние продукта находится в `docs/development_status.md`, подробности отдельных работ — в `docs/worklog/`, заметные изменения — в `CHANGELOG.md`.

## Источники истины

1. Код, миграции, тесты и слитые PR.
2. `docs/development_status.md`.
3. `docs/private_pool_inventory.json` и `docs/private_pool_inventory.md`.
4. `docs/stabilization_policy.md`.
5. Этот документ и worklog.

## Предметная граница продукта

Velvet Archive — отдельный архивный бот для создателя и преимущественно единоличного использования.

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
- staging, backup/restore automation, метрики, тесты и документация.

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

- application layer и composition root;
- media quality;
- publication domain;
- characters, stories и references;
- archive, preview и public archive;
- discussions, ingest, insights, rankings, activity и relink;
- core config и access middleware.

## Фазы 8–11. Управление и production foundation

Статус: завершены.

- Фаза 8: Supervisor, restart/update/rollback и Codex workflow;
- Фаза 9: application use cases владельца;
- Фаза 10: access boundaries и центр ошибок;
- Фаза 11: Python 3.13, PostgreSQL 16, Docker, restore drill и release workflow.

## Фазы 12–17. Архитектурная очистка P1

Статус: завершены.

- удалён SQL из части handlers;
- добавлен `PublicationActions`;
- разделены analytics management и owner reply-формы;
- multi-story перенесён в domain repositories;
- удалены runtime monkeypatch-мосты;
- compatibility installers стали безопасными фасадами/no-op.

## Фаза 18. Публичная граница PostgreSQL

Статус: завершена, private-pool baseline 0/0.

Завершённые срезы:

- 18A: `Database.acquire()`, character и story repositories;
- 18B: archive и public archive;
- 18C: references;
- 18D: media quality;
- 18E: publication repository;
- 18F–18L: полный discussion-контур;
- 18M: AST-инвентаризация и контролируемый baseline;
- 18N: `ArchivePreviewRepository`;
- 18O: `PublicationValidationRepository`;
- 18P: `PublicationDraftRepository`;
- 18Q: `SystemRepository`;
- 18R: `PromptResultReportRepository`;
- 18S: `PaletteCompositionReportRepository`;
- 18T: `VelvetFormattingReportRepository`;
- 18U: `QualityCalibrationRepository`;
- 18V: `AIQualityRepository` и его активный schema compatibility facade;
- 18W: `MediaAIRepository` в `ai_vision.py`;
- 18X: `ErrorIncidentRepository` в `error_center.py`;
- 18Y: `ReliableMediaAIRepository` в `ollama_vision.py`;
- 18Z: `ResilientMediaAIRepository` в `resilient_ai_vision.py`;
- 18AA: runtime-hardened `BackupService` в `backup_runtime.py`;
- 18AB: базовый `BackupService` в `backup_service.py`;
- 18AC: Telegram import persistence в `telegram_export_import.py`;
- 18AD: public media lookup query в `public_media_lookup.py`;
- 18AE: discussion thread links и analytics reactions;
- 18AF: alias management;
- 18AG: character aliases;
- 18AH: analytics dashboard;
- 18AI: analytics review и classification workflows;
- 18AJ: channel post ingest и channel statistics;
- 18AK: quality summary, issue pages и broken-check reset;
- 18AL: media-set discovery, decisions, creation, duplicate conversion и deletion;
- 18AM: `MediaSetAIRepository`, semantic profile loading и candidate persistence.

Текущий результат:

- первоначально: 130 внешних обращений в 35 production-файлах;
- после 18N: 128 обращений в 34 файлах;
- после 18O: 126 обращений в 33 файлах;
- после 18P: 118 обращений в 32 файлах;
- после 18Q: 116 обращений в 31 файле;
- после 18R: 115 обращений в 30 файлах;
- после 18S: 114 обращений в 29 файлах;
- после 18T: 113 обращений в 28 файлах;
- после 18U: 110 обращений в 27 файлах;
- после 18V: 100 обращений в 25 файлах;
- после 18W: 96 обращений в 24 файлах;
- после 18X: 88 обращений в 23 файлах;
- после 18Y: 86 обращений в 22 файлах;
- после 18Z: 84 обращений в 21 файле;
- после 18AA: 82 обращения в 20 файлах;
- после 18AB: 67 обращений в 19 файлах;
- после 18AC: 63 обращения в 18 файлах;
- после 18AD: 62 обращения в 17 файлах;
- после 18AE: 60 обращений в 15 файлах;
- после 18AF: 58 обращений в 14 файлах;
- после 18AG: 53 обращения в 13 файлах;
- после 18AH: 45 обращений в 12 файлах;
- после 18AI: 36 обращений в 11 файлах;
- после 18AJ: 28 обращений в 10 файлах;
- после 18AK: 23 обращения в 9 файлах;
- после 18AL: 14 обращений в 8 файлах;
- после 18AM: 12 обращений в 7 файлах;
- legacy query-модули и application-service direct DB access полностью удалены из baseline;
- новые или изменённые private pool access блокируются CI;
- semantic grouping, title/reason/score остаются в application service, DB loading и candidate transaction находятся в отдельном repository;
- SQL, claim locking, lifecycle, schema-compatible pagination, owner decisions, error acknowledgment/digest, AI response-version, backup schedule, retention, validation, discussion linking, reaction persistence, alias-management, character-alias, analytics-dashboard, analytics-review, channel-analytics, quality-audit, media-set и media-set-AI semantics завершённых срезов сохранены.

Фаза 18 закрыта полностью; следующий измеримый долг хранится в `docs/p2_stability_inventory.*`.

## Фаза 19. Velvet AI operations

Статус: завершена.

- полное меню качества;
- постоянный журнал AI-заданий;
- единый lifecycle `pending/processing/ready/error/interrupted`;
- сравнение с референсом, промт/результат, палитра, оформление и медиасеты;
- callback-контракты и PostgreSQL integration tests.

## Фаза 20. Удалённая эксплуатация Supervisor

Статус: код завершён, живая Windows-проверка обязательна.

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

# Линия C. Исторический план раннего рефакторинга

Эта секция сохранена для совместимости старого CI. Ранний аукционный план относится к другому продукту и не используется при выборе задач Velvet Archive.

# Открытые обязательства

## Немедленная эксплуатационная проверка

1. Обновить локальный `main` и перезапустить Velvet Bot.
2. Проверить основные AI- и медиасет-кнопки на реальном боте.
3. Проверить Supervisor self-restart на Windows.
4. Проверить Supervisor update-and-restart.
5. Зафиксировать Telegram success/error отчёт bootstrap.

## P2

1. P2A: поддерживать AST-инвентаризацию; multi-story callbacks переведены на acknowledgment до тяжёлого рендера.
2. P2B: late/missing callback baseline закрыт 0; quality callbacks подтверждаются до reload UI.
3. P2C: publication compensation/isolation boundaries классифицированы; unresolved broad baseline 70 → 68.
4. Подготовить staging-бота и staging-базу.
5. Провести независимый backup/restore drill.
6. Добавить зашифрованную внешнюю репликацию backup.
7. Добавить метрики длительности и ошибок AI-задач.

## P3

1. Постепенный статический анализ типов.
2. Удаление неиспользуемых compatibility-фасадов.
3. Закрытый container registry.
4. Расширенные release notes.

# Правило выбора следующей задачи

Перед работой агент обязан:

1. определить линию и фазу;
2. проверить предметную границу;
3. обосновать новый код улучшением существующей функции;
4. прочитать актуальный status, inventory и worklog;
5. создать стартовую запись;
6. определить измеримые критерии готовности;
7. закрыть запись проверками, PR/commit, остатком и следующим шагом.

Работа не считается завершённой, пока её итог не записан в проект.


## Завершение Фазы 18

Фаза 18 полностью закрыта: private-pool baseline уменьшен с 130 обращений в 35 production-файлах до 0/0. Persistence медиасетов вынесен в repositories, SQL удалён из трёх Telegram handlers, discussion compatibility делегирует каноническому dashboard, а оставшийся quality-set facade использует публичную границу. Новые внешние `_require_pool()` блокируются AST-контрактом.
