# Workspace taxonomy catalog

## Контекст

Владелец проекта утвердил документ `docs/requirements/workspace_product.md` как каноническое ТЗ пользовательских пространств. Пункт 15 требует поэтапно убрать глобальные захардкоженные каталоги из экранов личных архивов.

## Цель

Перевести чтение приватного и публичного каталога личного workspace на его собственные категории, вселенные, истории и `workspace_character_story_links`, сохранив системный Velvet Anatomy на совместимом legacy-контуре.

## До изменений

- пользовательские категории и вселенные безопасно хранились в workspace-таблицах;
- карточки личных персонажей уже могли получать workspace taxonomy;
- публичные фильтры продолжали строиться по `CATEGORY_ORDER`, `UNIVERSE_ORDER`, `character_stories` и `character_story_links`;
- одинаковые ключи в разных архивах хранились независимо, но старый публичный каталог не показывал их собственные подписи и истории.

## Реализовано

- добавлен канонический каталог требований `docs/requirements/`;
- `character_directory.py` получил явный `workspace_id` во всех операциях чтения и изменения;
- системный workspace `1` продолжает использовать прежний `CharacterDirectoryService`;
- личные workspace читают `workspace_categories`, `workspace_universes`, `workspace_stories` и `workspace_character_story_links`;
- публичные категории и вселенные используют собственные label, emoji и sort order;
- обязательность истории определяется `workspace_universes.requires_story`;
- персонаж вселенной с обязательной историей скрывается из публичного каталога до назначения активной истории;
- публичная видимость медиа сохраняет прежние правила `is_public`, +18, размера файла и активной доработки;
- primary story берётся из workspace-связей, а не из legacy `characters.story_id`;
- чужой `character_id` и `story_id` блокируются workspace scope;
- системная агрегация `games` сохранена только для Velvet Anatomy и не навязывается пользовательским вселенным.

### Риски и ограничения

- этот срез переводит каталог и фильтры, но не все старые inline-пикеры редактирования системного архива;
- сохранение медиа, references, publications, analytics и team roles остаются отдельными этапами канонического ТЗ;
- системный workspace намеренно остаётся на legacy story tables до отдельной миграции без изменения текущей выдачи Velvet Anatomy.

## После завершения

Личный публичный архив отображает только taxonomy выбранного workspace. Одинаковые ключи категорий, вселенных и историй в соседних архивах не влияют друг на друга. Приватный каталог также может получать workspace-scoped summaries и карточки через совместимый facade.

### Миграции и совместимость

Новая SQL-миграция не требуется. Срез использует таблицы миграций `903_workspace_product_access.sql`, `904_workspace_character_taxonomy.sql` и `905_workspace_character_management.sql`.

Совместимость:

- прежние вызовы без `workspace_id` продолжают работать для системного workspace `1`;
- старые константы и legacy story tables не удаляются;
- новые параметры добавлены как keyword-only со значениями по умолчанию.

### Проверки

Добавлены проверки:

- каноническое ТЗ присутствует в репозитории;
- facade принимает workspace scope;
- собственные label и emoji доходят до публичных фильтров;
- primary workspace story отображается в карточке;
- requires_story скрывает незавершённого персонажа;
- одинаковые ключи разрешены в разных workspace;
- чужой character/story ID не пересекает границу архива;
- navigation inventory обновлён после добавления Python-модуля.

### PR и commit

Ветка: `agent/workspace-taxonomy-catalog`.

PR создаётся после первого полного CI-прогона. Финальный merge commit будет добавлен в историю GitHub.

### Незавершённое

Следующие этапы по ТЗ:

1. workspace-aware inline-пикеры редактирования категории, вселенной и истории;
2. workspace scope при сохранении медиа и автоматической архивации;
3. references;
4. publications;
5. analytics;
6. управление ролями `admin`, `editor`, `reviewer`, `viewer` через UI.
