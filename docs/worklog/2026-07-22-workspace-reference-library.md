# Workspace-aware reference library and comparison

- Дата: 2026-07-22
- ID: workspace-reference-library
- Линия/фаза: Workspace product / references isolation
- Статус: завершено
- Ветка: `agent/workspace-reference-library`
- Базовый commit: `b15757c105a911c3cc17b1b9730c4699be62b68b`

## Перед началом

### Цель

Продолжить каноническое ТЗ `docs/requirements/workspace_product.md` и перевести хранение, просмотр, удаление и Qwen-сравнение референсов на workspace boundary.

### Исходный контекст

Персонажи и медиа уже были изолированы по workspace, но `character_references` и `reference_comparison_reports` не содержали workspace ID. Legacy-команды искали персонажа в системном архиве, upload-сессия фиксировала только character ID и имя, а callback и compare-команда работали с глобальными идентификаторами.

### Планируемый объём

- добавить workspace ID в референсы и отчёты сравнения;
- запретить связь reference/character/report между соседними пространствами на уровне PostgreSQL;
- сделать ReferenceRepository и сервис workspace-aware с legacy default для system workspace;
- фиксировать workspace в upload-сессии;
- добавить personal-workspace router перед legacy references;
- поддержать фото, изображения-документы, альбомный просмотр, удаление, callbacks и inline;
- применять editor/reviewer/viewer roles и статусы modules `references`/`qwen`;
- сохранить старый системный Velvet без изменения команд;
- добавить contract и PostgreSQL regression tests.

### Критерии готовности

- одинаковые имена персонажей и одинаковые изображения не пересекаются между workspace;
- foreign reference ID нельзя прочитать или удалить через соседнее пространство;
- comparison report нельзя связать с reference соседнего workspace;
- upload-сессия продолжает писать в исходный workspace после переключения активного архива;
- выключенный references/qwen module блокирует прямые команды и callbacks;
- personal router выполняется раньше legacy reference handlers;
- system workspace `1` сохраняет прежний интерфейс;
- tests, type-check, Docker build и notes contract зелёные.

### Риски и ограничения

- callback_data остаётся компактным и содержит character/reference ID без workspace ID; workspace повторно определяется из активного контекста и проверяется запросом;
- локальная модель Qwen и глобальный AI provider остаются общими runtime-ресурсами, но право запуска определяется настройками workspace;
- Telegram media-group используется как альбомный просмотр; отдельные именованные DB-альбомы не вводятся этим срезом;
- новая миграция обязательна, так как прежняя схема не могла обеспечить tenant constraints.

## После завершения

### Фактически сделано

- миграция `906_workspace_references.sql` добавляет `workspace_id` в `character_references` и `reference_comparison_reports`;
- существующие строки backfill-ятся из `characters.workspace_id`;
- добавлены составные FK `(workspace_id, character_id)` и `(workspace_id, reference_id)`;
- ReferenceRepository фильтрует add/delete/count/list/page по workspace;
- модели reference и character page возвращают workspace ID;
- facade и owner application поддерживают optional workspace ID с legacy default `1`;
- ReferenceUploadSession фиксирует workspace ID и character ID;
- personal reference router перехватывает `/refadd`, `/ref`, `/refs`, `/refdel`, `/compare_ref`, загрузки и callbacks;
- фото и изображения-документы сохраняются в выбранный личный архив;
- альбомная и inline-выдача формируются только из текущего workspace;
- Qwen comparison требует роли reviewer, references module, qwen module и workspace qwen setting;
- audit события личной библиотеки содержат workspace ID;
- legacy reference routers остаются контуром system workspace.

### Миграции и совместимость

Добавлена миграция `906_workspace_references.sql`.

Системные вызовы, не передающие workspace ID, продолжают использовать `DEFAULT_WORKSPACE_ID = 1`. Старые таблицы и команды не удаляются.

### Проверки

Добавлены contract и PostgreSQL regression tests на:

- фиксацию workspace/character в reference upload session;
- workspace-aware service API;
- порядок personal router до legacy references;
- наличие составных FK в миграции;
- одинаковые character names и file unique IDs в разных workspace;
- отсутствие чтения через foreign workspace;
- запрет foreign delete;
- запрет comparison report с reference соседнего workspace;
- успешное сохранение валидного workspace comparison report.

Generated architecture и repository-layout inventories сохранены с их каноническими baseline labels, а P2 inventory поднят до schema version `49` с нулём risky callbacks.

### PR и commit

PR: `#285 Isolate reference libraries by workspace`. Финальный merge commit фиксируется после зелёного CI.

### Незавершённое

- публикации и очереди по workspace;
- analytics по workspace;
- Telegram UI ролей team;
- именованные коллекции/альбомы референсов, если они будут утверждены отдельным продуктовым требованием.

### Следующий шаг

Перевести публикационный workflow и очереди подготовки постов на workspace boundary.
