# Сессия: P3D Channel Analytics alias retirement

- Дата: 2026-07-21
- ID: `2026-07-21-p3d-channel-analytics-alias-retirement`
- Линия/фаза: P3D compatibility alias retirement
- Статус: `частично`
- Ветка: `agent/p3d-retire-channel-analytics-alias`
- Базовый commit: `f0bfff96af4d087aa9485a158b08f405ce38ef74`

## Перед началом

### Цель

Удалить последний compatibility alias `velvet_bot.handlers.channel_analytics`, перевести остаточные tests на canonical analytics controller и завершить P3D с нулевым handler alias inventory.

### Исходный контекст

После последовательных archive/reference, character/story, quality, core, backup, Supervisor и analytics срезов в `velvet_bot/handlers` остался один alias. Production consumers уже равны `0 / 0 / 0`; пять repository references относятся к тестам и inventory scripts.

Удаление было отложено из-за прямого чтения `Message.views` и `Message.forward_count` в `parse_channel_post`. Упрощённые Telegram objects и отдельные update variants могут не предоставлять эти optional counters как атрибуты.

### Планируемый объём

- безопасно читать optional Telegram counters через `getattr(..., None)`;
- добавить regression-тест сообщения без views/forward_count;
- перевести P2 channel boundary test на canonical controller;
- обновить P3C и residual contracts на отсутствие всех handler aliases;
- удалить `velvet_bot/handlers/channel_analytics.py`;
- обновить architecture и alias-consumer inventories;
- перевести указатель следующего структурного среза с P3D на P3E.

### Критерии готовности

- `velvet_bot/handlers` содержит 0 implementations и 0 aliases;
- production legacy consumers остаются 0 / 0 / 0;
- missing alias references остаются 0;
- channel ingest принимает сообщение без views/forward_count и сохраняет `None`;
- пять analytics routers сохраняют прежний порядок;
- callbacks, commands, SQL и пользовательское поведение не изменяются;
- полный CI проходит.

### Риски и ограничения

Срез не переносит `velvet_bot/channel_analytics.py` и не меняет persistence layout. Это отдельная P3E-задача. Расчёты статистики, dashboard, callback schema и таблицы PostgreSQL не изменяются.

## После завершения

### Фактически сделано

Работа начата. Итог заполняется после изменений и inventory update.

### Миграции и совместимость

Миграции базы данных не планируются. Исторический import `velvet_bot.handlers.channel_analytics` будет удалён после перевода всех repository consumers.

### Проверки

Запланированы channel analytics unit tests, P2 boundary, P3C analytics, P3D residual, generated inventories и полный GitHub CI.

### PR и commit

PR создаётся после завершения ветки.

### Незавершённое

До завершения требуется внести кодовые изменения, удалить alias и обновить машинные inventories.

### Следующий шаг

После закрытия P3D перейти к P3E repository/root-module layout inventory и выбрать первый домен для отдельного физического переноса.
