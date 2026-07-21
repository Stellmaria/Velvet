# Workspace requirements and taxonomy directory catalog

## Цель

Закрепить пользовательское ТЗ «Моё пространство» как нормативный проектный контракт и начать следующий этап перевода старых каталогов персонажей с глобальных констант на workspace taxonomy.

## До начала

- multi-workspace foundation, product access и taxonomy уже существуют;
- личные персонажи, aliases и связи с историями изолированы по workspace;
- системный Velvet Anatomy продолжает использовать legacy-каталог;
- требования до этого среза не были закреплены отдельным нормативным документом.

## Реализовано

- добавлено официальное ТЗ `docs/specifications/workspace_requirements.md`;
- закреплён приоритет ТЗ над устаревшими экранами и вспомогательной документацией;
- добавлен workspace-scoped directory catalog domain;
- категории, вселенные и истории читаются из таблиц конкретного workspace;
- одинаковые taxonomy keys в разных пространствах не пересекаются;
- добавлен личный экран `/wcatalog`;
- доступны фильтры по категориям, вселенным и историям workspace;
- карточки и страницы проверяют workspace membership и включённые модули;
- системный workspace 1 остаётся на `/characters`;
- прямой callback другого или недоступного workspace блокируется.

### Риски и ограничения

- новый `/wcatalog` является первым рабочим контуром; legacy `/characters` пока остаётся системным;
- комбинированный фильтр категория + вселенная + история будет добавляться отдельным срезом;
- редактирование taxonomy через inline-кнопки персонажа пока не входит в этот PR;
- публичный read-only каталог будет переведён на тот же domain после административного контура.

### Миграции и совместимость

- SQL-миграции не добавлялись;
- существующие таблицы `workspace_categories`, `workspace_universes`, `workspace_stories` и `workspace_character_story_links` используются без изменения схемы;
- системный Velvet Anatomy не меняет существующее поведение.

### Проверки

- contract test нормативного ТЗ;
- contract test порядка router registration;
- PostgreSQL regression test workspace isolation;
- проверки category/universe/story filters;
- проверка запрета cross-workspace story id;
- полный CI после открытия PR.

## После завершения

Следующий срез должен подключить workspace taxonomy непосредственно к редактированию карточки персонажа, сохранению медиа и референсам, затем перевести публичный каталог.

### PR и commit

Будут заполнены после открытия PR и успешного CI.

### Незавершённое

- inline-редактор категории, вселенной и историй персонажа;
- комбинированные фильтры;
- workspace scope для references, publications и analytics UI;
- управление ролями команды;
- публичный workspace directory на новом domain.
