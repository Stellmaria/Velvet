# Workspace taxonomy catalog

- Дата: 2026-07-22
- ID: workspace-taxonomy-catalog
- Линия/фаза: Линия A / multi-workspace catalog
- Статус: `частично`
- Ветка: `agent/workspace-taxonomy-catalog`
- Базовый commit: `46446e9a3bbb0b7f789f24198f3334091aec7d86`

## Перед началом

### Цель

Закрепить утверждённые владельцем требования пользовательских пространств как каноническое ТЗ и перевести чтение приватного и публичного каталога личного workspace на его собственные категории, вселенные, истории и `workspace_character_story_links`.

### Исходный контекст

- пользовательские категории и вселенные уже безопасно хранились в workspace-таблицах;
- карточки личных персонажей уже могли получать workspace taxonomy;
- публичные фильтры продолжали строиться по `CATEGORY_ORDER`, `UNIVERSE_ORDER`, `character_stories` и `character_story_links`;
- одинаковые ключи в разных архивах хранились независимо, но старый публичный каталог не показывал их собственные подписи и истории;
- системный Velvet Anatomy должен сохранить текущее поведение без принудительного перевода на пользовательские таблицы.

### Планируемый объём

1. Добавить каталог канонических требований `docs/requirements/`.
2. Создать workspace-aware boundary каталога персонажей.
3. Подключить `workspace_id` к совместимому facade.
4. Перевести публичные категории, вселенные, истории и персонажей личного архива на workspace taxonomy.
5. Добавить PostgreSQL regression tests на изоляцию и обязательность истории.
6. Сохранить legacy-поведение системного workspace `1`.

### Критерии готовности

- утверждённое ТЗ находится в репозитории и явно объявлено обязательным;
- личный каталог читает label, emoji и sort order из таблиц текущего workspace;
- primary story берётся из `workspace_character_story_links`;
- `requires_story` влияет на публичную готовность персонажа;
- чужие `character_id` и `story_id` блокируются workspace scope;
- системный Velvet Anatomy работает через прежний контур;
- полный CI зелёный.

### Риски и ограничения

- срез переводит каталог и фильтры, но не все старые inline-пикеры редактирования;
- сохранение медиа, references, publications, analytics и team roles остаются отдельными этапами канонического ТЗ;
- системный workspace намеренно остаётся на legacy story tables до отдельного безопасного этапа;
- публичные SQL-фильтры должны сохранить существующие ограничения по +18, размеру файлов и активной доработке.

## После завершения

### Фактически сделано

- добавлен канонический каталог требований `docs/requirements/`;
- `docs/requirements/workspace_product.md` содержит утверждённое ТЗ пользовательских пространств;
- `character_directory.py` получил явный `workspace_id` в операциях чтения и изменения;
- системный workspace `1` продолжает использовать прежний `CharacterDirectoryService`;
- личные workspace читают `workspace_categories`, `workspace_universes`, `workspace_stories` и `workspace_character_story_links`;
- публичные категории и вселенные используют собственные label, emoji и sort order;
- обязательность истории определяется `workspace_universes.requires_story`;
- персонаж вселенной с обязательной историей скрывается из публичного каталога до назначения активной истории;
- публичная видимость медиа сохраняет правила `is_public`, +18, размера файла и активной доработки;
- primary story берётся из workspace-связей, а не из legacy `characters.story_id`;
- чужой `character_id` и `story_id` блокируются workspace scope;
- системная агрегация `games` сохранена только для Velvet Anatomy и не навязывается пользовательским вселенным.

### Миграции и совместимость

Новая SQL-миграция не требуется. Срез использует таблицы миграций:

- `903_workspace_product_access.sql`;
- `904_workspace_character_taxonomy.sql`;
- `905_workspace_character_management.sql`.

Совместимость:

- прежние вызовы без `workspace_id` продолжают работать для системного workspace `1`;
- старые константы и legacy story tables не удаляются;
- новые параметры добавлены как keyword-only со значениями по умолчанию;
- пользовательский каталог не изменяет системные записи Velvet Anatomy.

### Проверки

Добавлены проверки на:

- наличие канонического ТЗ в репозитории;
- поддержку workspace scope в facade;
- собственные label и emoji в публичных фильтрах;
- primary workspace story в карточке;
- скрытие незавершённого персонажа при `requires_story`;
- одинаковые ключи в разных workspace;
- запрет чужого character/story ID;
- актуальность Telegram navigation inventory.

CI PR #281 запущен. Первый прогон выявил только несоответствие формату worklog; рабочая запись приведена к обязательному контракту. Финальный результат проверок фиксируется перед merge.

### PR и commit

- PR: `#281 Use workspace taxonomy in character catalogs`;
- ветка: `agent/workspace-taxonomy-catalog`;
- текущий head до исправления worklog: `0fdb07896f23e33d064d0ee3edd9b84838dda9b6`;
- merge commit будет зафиксирован GitHub после зелёного CI.

### Незавершённое

1. Workspace-aware inline-пикеры редактирования категории, вселенной и истории.
2. Workspace scope при сохранении медиа и автоматической архивации.
3. References.
4. Publications.
5. Analytics.
6. Управление ролями `admin`, `editor`, `reviewer`, `viewer` через UI.

### Следующий шаг

После слияния каталога перевести inline-управление карточкой личного персонажа на динамические кнопки категорий, вселенных и историй текущего workspace, затем подключить workspace scope к сохранению медиа.
