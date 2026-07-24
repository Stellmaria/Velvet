# Сессия: persistence boundary черновиков watermark

- Дата: 2026-07-24
- ID: `2026-07-24-watermark-draft-persistence-boundary`
- Линия/фаза: workspace architecture cleanup
- Статус: `завершено`
- Ветка: `agent/watermark-draft-persistence-boundary`
- Базовый commit: `c29499bccdb6c9de358bb0eb6c240ab1fb07a506`

## Перед началом

### Цель

Перенести создание, изменение, undo и постановку в очередь draft watermark revisions из Telegram controller в `WatermarkRepository` и нативный `WatermarkService`.

### Исходный контекст

`workspace_product_experience.py` напрямую выполнял SQL для `watermark_jobs` и `watermark_revisions`, обращался к `repository._database`, `_map_job`, `_map_revision`, `_settings_from_row`, `_current_query` и во время установки подменял методы `WatermarkService`. Отдельный `workspace_template_runtime.py` повторно подменял `create_job` и доставал database через private repository attribute.

### Планируемый объём

- сделать status новой revision явным параметром repository;
- добавить repository-операцию перевода draft/error revision в pending;
- добавить нативные draft-aware методы service;
- передавать workspace template и draft mode из core watermark flow;
- удалить persistence SQL и service monkeypatch из workspace controller;
- добавить unit, architecture и PostgreSQL integration coverage.

### Критерии готовности

- controller не содержит SQL watermark persistence и private repository access;
- `WatermarkService` не подменяется во время runtime installation;
- draft revision не захватывается worker до явной генерации;
- после генерации revision становится pending и доступна worker;
- устаревшую draft revision нельзя поставить в очередь после создания новой;
- полный CI зелёный.

### Риски и ограничения

UI formatter/keyboard и `_wake_krita` runtime patch пока не удаляются. Их перенос является отдельным presentation/runtime срезом. Схема БД не меняется.

## После завершения

### Фактически сделано

- `WatermarkRepository.create_job`, `create_revision` и `undo` получили явный revision status;
- добавлен атомарный `queue_revision()` с переходом `draft/error → pending` только для текущей revision;
- `WatermarkService` получил нативные draft-aware `create_job`, `revise`, `undo` и `generate`;
- core watermark flow явно загружает workspace template и создаёт draft;
- из `workspace_product_experience.py` удалены SQL, private repository mapping/access и runtime monkeypatch методов service;
- удалён устаревший `workspace_template_runtime.py` и его production installer;
- добавлены service, architecture и PostgreSQL integration tests для жизненного цикла `draft → pending → processing` и stale revision guard;
- обновлены repository layout и Telegram navigation generated inventories.

### Миграции и совместимость

Новые миграции не требуются. Существующие статусы `draft`, `pending`, `processing`, `ready`, `error`, callback data и Krita worker contract сохранены. Обычные вызовы service без `draft=True` продолжают создавать pending revisions, поэтому прежний API остаётся совместимым.

### Проверки

- focused compileall: success;
- focused service, architecture и PostgreSQL integration tests: success;
- tests `1816`: success, 1291 тест;
- type check `469`: success;
- Docker build `1225`: success;
- project notes contract `1095`: success;
- repository layout inventory: regenerated and checked;
- Telegram navigation inventory: regenerated and checked.

### PR и commit

- PR: `#313 Move watermark draft persistence behind domain boundary`;
- ветка: `agent/watermark-draft-persistence-boundary`;
- implementation head перед финализацией журнала: `4afa30a710b86e07000801a241e700e622a572f8`.

### Незавершённое

- после merge выполнить smoke test: открыть watermark draft, изменить параметры, запустить preview, проверить повторное нажатие и undo;
- formatter/keyboard patches и `_wake_krita` остаются следующим отдельным срезом.

### Следующий шаг

Вынести watermark UI formatter/keyboard и Krita wake policy из runtime installer в явные presentation contracts.
