# Сессия: P3D Analytics handler alias retirement

- Дата: 2026-07-20
- ID: `2026-07-20-p3d-analytics-alias-retirement`
- Линия/фаза: P3D compatibility alias retirement
- Статус: `завершено`
- Ветка: `agent/p3d-analytics-alias-retirement`
- Базовый commit: `d91fc91b15ccd75814bca843b615a009f8f09ad1`

## Перед началом

### Цель

Удалить восемь завершивших миграцию analytics compatibility aliases, перевести оставшиеся тесты на canonical presentation controllers и оставить только отдельно отложенный `channel_analytics`.

### Исходный контекст

После P3D-Supervisor в `velvet_bot.handlers` оставалось девять module aliases. Восемь dashboard, discussion и management aliases уже не участвовали в production Router composition, но сохранялись из-за regression-тестов. `channel_analytics` намеренно не входит в этот срез из-за отдельной ошибки ingest-контракта `Message.views`.

### Планируемый объём

- перевести analytics dashboard, management и discussion tests на canonical modules;
- удалить восемь non-channel analytics aliases;
- обновить P3C и residual handler contracts;
- обновить architecture и handler-consumer inventories;
- сохранить порядок пяти analytics routers;
- не изменять `analytics_controllers.channel`.

### Критерии готовности

- восемь non-channel analytics alias-файлов отсутствуют;
- `channel_analytics` остаётся единственным handler alias;
- production legacy imports и duplicate registrations остаются равны нулю;
- missing alias references остаются равны нулю;
- полный CI проходит.

### Риски и ограничения

Срез меняет только import compatibility и архитектурные тесты. Расчёт аналитики, callback schema, dashboard, discussion insights и management actions не меняются. Миграции PostgreSQL не требуются. Отложенный channel ingest не редактируется.

## После завершения

### Фактически сделано

- tests dashboard, management и discussion переведены на canonical analytics controllers;
- удалены aliases `analytics_dashboard`, `analytics_dashboard_overrides`, `analytics_discussion_overrides`, `analytics_management`, `analytics_management_aliases`, `analytics_management_common`, `analytics_management_publications`, `analytics_management_tags`;
- P3C contract теперь проверяет удаление этих файлов и сохранение deferred channel alias;
- residual handler contract фиксирует единственный остаточный alias `channel_analytics`;
- architecture inventory уменьшен с 9 до 1 alias;
- handler consumer inventory уменьшен с 9 до 5 consumer-файлов и с 25 до 5 references;
- production Router order и analytics functionality не менялись.

### Миграции и совместимость

Миграции базы данных не требуются. Исторические Python imports восьми удалённых aliases больше не поддерживаются. Canonical modules и callback contracts остаются прежними.

### Проверки

Обновлены analytics dashboard, phase 2 callbacks, phase 5 discussion, phase 14 split, P3C analytics, residual handler и machine inventory tests. Полный GitHub CI запускается в PR.

### PR и commit

PR создаётся из ветки `agent/p3d-analytics-alias-retirement`; итоговый merge commit фиксируется после зелёного CI.

### Незавершённое

В `velvet_bot.handlers` остаётся только `channel_analytics`. Его удаление отложено до отдельного исправления `Message.views` и снятия ограничения на изменение channel controller.

### Следующий шаг

Перейти к public archive access и watermark workflow отдельными миграционными срезами: членство канала, download policy, watermark approval, admin metrics и очередь доработки.
