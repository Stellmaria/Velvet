# Сессия: P3D Channel Analytics alias retirement

- Дата: 2026-07-21
- ID: `2026-07-21-p3d-channel-analytics-alias-retirement`
- Линия/фаза: P3D compatibility alias retirement
- Статус: `завершено`
- Ветка: `agent/p3d-retire-channel-analytics-alias`
- Базовый commit: `f0bfff96af4d087aa9485a158b08f405ce38ef74`

## Перед началом

### Цель

Удалить последний compatibility alias `velvet_bot.handlers.channel_analytics`, перевести остаточные tests на canonical analytics controller и завершить P3D с нулевым handler alias inventory.

### Исходный контекст

После последовательных archive/reference, character/story, quality, core, backup, Supervisor и analytics срезов в `velvet_bot/handlers` оставался один alias. Production consumers уже были равны `0 / 0 / 0`; пять repository references относились только к тестам и inventory scripts.

Предыдущий worklog откладывал alias вместе с возможным hardening optional `Message.views`/`Message.forward_count`. Проверка показала, что alias не участвует в ingest-контракте и не нужен для его совместимости: canonical controller импортирует тот же transport-neutral analytics module напрямую. Поэтому runtime hardening counters не смешивался с физическим compatibility removal без подтверждённой ошибки этого контракта.

### Планируемый объём

- перевести P2 channel boundary test на canonical controller;
- обновить P3C и residual contracts на отсутствие всех handler aliases;
- удалить `velvet_bot/handlers/channel_analytics.py`;
- обновить architecture и alias-consumer inventories;
- перевести указатель следующего структурного среза с P3D на P3E;
- не менять channel analytics runtime, SQL и пользовательское поведение.

### Критерии готовности

- `velvet_bot/handlers` содержит 0 implementations и 0 aliases;
- production legacy consumers остаются 0 / 0 / 0;
- missing alias references остаются 0;
- пять analytics routers сохраняют прежний порядок;
- callbacks, commands, SQL и пользовательское поведение не изменяются;
- generated inventories совпадают с working tree;
- полный CI проходит.

### Риски и ограничения

Срез не переносит `velvet_bot/channel_analytics.py`, не меняет persistence layout и не исправляет неподтверждённые runtime-сценарии optional Telegram counters. Это отдельная задача только при воспроизводимом ingest failure. Расчёты статистики, dashboard, callback schema и таблицы PostgreSQL не изменяются.

## После завершения

### Фактически сделано

- P2 channel analytics boundary test переведён с `velvet_bot.handlers.channel_analytics` на canonical controller;
- P3C analytics contract теперь проверяет importability canonical channel controller и отсутствие всех девяти исторических analytics aliases;
- residual handler contract требует 0 implementations и 0 aliases;
- удалён последний файл `velvet_bot/handlers/channel_analytics.py`;
- architecture inventory обновлён до 0 legacy handler files, 0 implementations и 0 facades;
- alias-consumer inventory обновлён до 0 aliases, 0 missing references и двух допустимых dynamic-prefix sentinels;
- generator scripts теперь указывают следующий структурный этап P3E;
- порядок пяти analytics routers и runtime behavior не менялись.

### Миграции и совместимость

Миграции базы данных не требуются. Исторический import `velvet_bot.handlers.channel_analytics` больше не поддерживается. Canonical module `velvet_bot.presentation.telegram.routers.analytics_controllers.channel`, команды, callbacks и analytics persistence остаются прежними.

### Проверки

Обновлены P2 channel boundary, P3C analytics, P3D residual contracts, architecture inventory и handler alias inventory. Полный GitHub CI запускается в PR.

### PR и commit

PR создаётся из ветки `agent/p3d-retire-channel-analytics-alias`; итоговый squash commit фиксируется после зелёного CI.

### Незавершённое

Handler alias debt закрыт полностью. Вне этого среза остаются восемь активных runtime compatibility components, 117 корневых Python-модулей и неоднородный repository layout. Optional counter hardening выполняется только при отдельной воспроизводимой ingest-ошибке.

### Следующий шаг

Перейти к P3E: построить измеримый inventory расположения repositories/root modules и выбрать один небольшой домен для отдельного физического переноса без изменения поведения.
