# Сессия: P3D quality и Velvet AI alias retirement

- Дата: 2026-07-20
- ID: `2026-07-20-p3d-quality-alias-retirement`
- Линия/фаза: P3D compatibility retirement
- Статус: `завершено`
- Ветка: `agent/p3d-quality-alias-retirement`
- Базовый commit: `539d71a072a6149240dae5ca28980b0fd88739d0`

## Перед началом

### Цель

Удалить временные compatibility aliases quality/Velvet AI после перевода всех repository consumers на canonical presentation-модули.

### Исходный контекст

Production Router уже использовал `velvet_bot.presentation.telegram.routers.quality_operations_controllers`, но часть regression- и boundary-тестов продолжала импортировать старые `velvet_bot.handlers.*` aliases. Инвентарь фиксировал 35 alias-файлов, 35 consumer-файлов и 74 references.

### Планируемый объём

- перевести quality, media-set и Velvet AI тесты на canonical imports;
- удалить 10 compatibility alias-файлов;
- сохранить прежнее тестовое покрытие callback, safe-edit, job compensation и preview fallback;
- обновить handler consumer inventory и architecture layout inventory;
- не менять runtime-поведение Qwen, media-quality workers и Telegram Router;
- не затрагивать отложенный channel analytics controller.

### Критерии готовности

- удалённые alias-модули больше не импортируются из repository tests;
- canonical modules остаются единственными владельцами router implementations;
- alias inventory показывает 25 aliases, 0 missing references и 0 production legacy consumers;
- architecture inventory показывает 25 handler aliases и 58 active routers;
- полный CI проходит.

### Риски и ограничения

Некоторые тесты monkeypatch-ят module globals, поэтому imports должны указывать непосредственно на canonical module object. Простая переэкспортная обёртка сохранила бы технический долг и не считалась бы закрытием среза.

## После завершения

### Фактически сделано

- тесты quality AI, preview, quality center, duplicates, operations, media sets и set AI переведены на canonical presentation imports;
- тесты Velvet AI prompt/result, formatting и palette/composition переведены на canonical presentation imports;
- удалены aliases `quality_ai`, `quality_ai_preview`, `quality_center`, `quality_duplicates`, `quality_operations`, `quality_set_ai`, `quality_sets`, `velvet_ai`, `velvet_ai_formatting`, `velvet_ai_visual`;
- P3C quality controller test теперь проверяет отсутствие удалённых alias-файлов и сохраняет compatibility-проверку только для ещё существующего `backup_center`;
- handler alias inventory уменьшен с 35 до 25 aliases, с 35 до 23 consumer-файлов и с 74 до 57 references;
- architecture inventory синхронизирован: 25 aliases, 0 implementations, 58 active routers.

### Миграции и совместимость

SQL-миграции не требуются. Production callback contracts, Router order и business behavior не меняются. Удаляется только repository-level compatibility API, для которого consumers уже переведены на canonical paths.

### Проверки

Обновлены существующие regression- и architecture-тесты, а также оба машинных inventory. Полный GitHub CI запускается в PR.

### PR и commit

PR будет создан из ветки `agent/p3d-quality-alias-retirement`; итоговый merge commit фиксируется после зелёного CI.

### Незавершённое

В P3D остаются 25 aliases: analytics, core/owner, publication, backup, Supervisor, system и watermark. `channel_analytics` остаётся отложенным до отдельного исправления контракта Telegram `Message.views`.

### Следующий шаг

Продолжить P3D-Core: перевести owner, error center, publication, backup, system и watermark tests на canonical modules и удалить следующую связанную группу aliases. После закрытия P3D перейти к P3E persistence layout и P3F gradual typing.
