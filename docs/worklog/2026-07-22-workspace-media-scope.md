# Workspace-aware media save and automatic archive

- Дата: 2026-07-22
- ID: workspace-media-scope
- Линия/фаза: Workspace product / media archive isolation
- Статус: завершено
- Ветка: `agent/workspace-media-scope`
- Базовый commit: `d83ee6f4c3aa89e3dac12aaaf6cbc158cd655217`

## Перед началом

### Цель

Продолжить каноническое ТЗ `docs/requirements/workspace_product.md` и перевести ручное сохранение медиа, отложенные `/save`-сессии и автоматическую архивацию Telegram-тем на workspace boundary.

### Исходный контекст

Персонажи, taxonomy и каталоги уже были изолированы по workspace. При этом команда `/save` продолжала использовать глобальный `resolve_character()` без workspace, а `SaveUploadSession` сохраняла только имя персонажа. Автоархивация искала всех персонажей по Telegram topic без tenant-фильтра.

### Планируемый объём

- разрешать имя и алиас персонажа только внутри активного workspace;
- фиксировать workspace и character ID в upload-сессии;
- повторно проверять editor role и archive module перед приёмом отложенного файла;
- определять workspace автоархивации по подключённому archive-чату;
- сохранять legacy system workspace для непривязанных старых archive-чатов;
- блокировать foreign character ID и одинаковые alias/name из соседнего пространства;
- добавить PostgreSQL regression tests;
- не добавлять миграцию без необходимости.

### Критерии готовности

- `/save Имя` использует активный workspace пользователя;
- одинаковые имена в разных workspace не пересекаются;
- одинаковые алиасы в разных workspace не пересекаются;
- переключение workspace после запуска десятиминутной сессии не меняет цель сохранения;
- отозванная роль или выключенный archive module прекращают отложенную загрузку;
- автоархивация topic принимает только персонажей workspace подключённого archive-чата;
- старый системный архив сохраняет совместимость;
- tests, type-check, Docker build и notes contract зелёные.

### Риски и ограничения

- системный workspace сохраняет прежний внешний access-контур для пользователей без workspace membership;
- topic ownership определяется по `workspace_channels(kind='archive')`;
- непривязанный archive-чат считается legacy system workspace;
- отдельный UI выбора workspace внутри `/save` не добавляется: используется активное пространство;
- новая SQL-миграция не требуется.

## После завершения

### Фактически сделано

- `resolve_character()` получил обязательную tenant-фильтрацию через optional `workspace_id`;
- системные aliases читаются из `character_aliases`, личные aliases из `workspace_character_aliases`;
- добавлена загрузка персонажа по `(workspace_id, character_id)`;
- `save_media_from_message()` принимает `workspace_id` и проверенный `resolved_character`;
- audit media-save включает workspace ID;
- `SaveUploadSession` сохраняет workspace ID и character ID;
- `/save` и mention-save разрешают активный workspace до поиска персонажа;
- личный workspace требует роль editor и включённый archive module;
- перед отложенной загрузкой доступ проверяется повторно;
- удалённый или перемещённый персонаж не может принять файл из старой сессии;
- auto-archive определяет workspace по archive channel и фильтрует topic links по нему;
- legacy database adapters поддерживаются без обязательного нового аргумента;
- непривязанные archive-чаты продолжают работать как system workspace.

### Миграции и совместимость

Новая миграция не добавлялась. Используются существующие колонки `characters.workspace_id`, таблицы `user_workspace_preferences`, `workspace_members`, `workspace_modules`, `workspace_channels`, `workspace_character_aliases` и `character_archive_topics`.

Системный workspace `1` остаётся совместимым со старым `/save` и непривязанными archive-чатами.

### Проверки

Добавлены contract и PostgreSQL regression tests на:

- фиксацию workspace/character в save session;
- workspace-aware API media-save;
- одинаковые имена и aliases в разных пространствах;
- запрет загрузки foreign character ID;
- выбор workspace по archive chat;
- исключение персонажа соседнего workspace из одной Telegram-темы;
- legacy fallback непривязанного чата к system workspace.

### PR и commit

PR будет создан после подготовки полного diff. Финальный merge commit фиксируется в GitHub.

### Незавершённое

- workspace-aware references;
- публикации и очереди по workspace;
- analytics по workspace;
- Telegram UI ролей team;
- кнопочная форма создания, rename, aliases, prompt и topic.

### Следующий шаг

Перевести библиотеку референсов и сравнение внешности на активный workspace, запретив связывать reference с персонажем соседнего архива.
