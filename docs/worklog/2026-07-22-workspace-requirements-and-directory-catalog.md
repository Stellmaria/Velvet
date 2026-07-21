# Сессия: Workspace requirements and taxonomy directory catalog

- Дата: 2026-07-22
- ID: `2026-07-22-workspace-requirements-and-directory-catalog`
- Линия/фаза: multi-workspace taxonomy migration
- Статус: `частично`
- Ветка: `agent/workspace-requirements-and-taxonomy-ui`
- Базовый commit: `46446e9a3bbb0b7f789f24198f3334091aec7d86`

## Перед началом

### Цель

Закрепить пользовательское ТЗ «Моё пространство» как нормативный проектный контракт и начать следующий этап перевода старых каталогов персонажей с глобальных констант на workspace taxonomy.

### Исходный контекст

Multi-workspace foundation, product access, taxonomy, личные персонажи, aliases и workspace-scoped связи с историями уже реализованы. Системный Velvet Anatomy продолжает использовать legacy-каталог. Требования до этого среза не были закреплены отдельным нормативным документом в репозитории.

### Планируемый объём

- добавить официальное ТЗ в `docs/specifications`;
- зафиксировать приоритет ТЗ над устаревшими экранами;
- создать workspace-scoped directory domain;
- добавить личный каталог с фильтрами по категориям, вселенным и историям;
- сохранить старый системный `/characters` без изменений;
- добавить regression tests workspace isolation.

### Критерии готовности

- ТЗ находится в репозитории и помечено нормативным;
- личный каталог читает taxonomy только выбранного workspace;
- одинаковые ключи разных workspace не пересекаются;
- прямой callback недоступного workspace блокируется;
- системный workspace 1 остаётся на прежнем каталоге;
- PostgreSQL regression tests подтверждают фильтры и cross-workspace isolation.

### Риски и ограничения

Новый `/wcatalog` является первым рабочим контуром. Legacy `/characters` пока остаётся системным. Комбинированный фильтр категория + вселенная + история, inline-редактор карточки и публичный read-only каталог будут добавляться отдельными срезами, чтобы не смешивать сразу все старые маршруты в один чрезмерно рискованный PR.

## После завершения

### Фактически сделано

- добавлено официальное ТЗ `docs/specifications/workspace_requirements.md`;
- закреплён приоритет ТЗ над устаревшими экранами и вспомогательной документацией;
- добавлен `domains/workspaces/directory_catalog.py`;
- категории, вселенные и истории читаются из таблиц конкретного workspace;
- одинаковые taxonomy keys в разных пространствах изолированы;
- добавлен личный экран `/wcatalog`;
- доступны фильтры по категориям, вселенным и историям workspace;
- карточки и страницы проверяют workspace membership и включённые модули;
- системный workspace 1 остаётся на `/characters`;
- direct callback другого или недоступного workspace блокируется;
- добавлены contract и PostgreSQL regression tests.

### Миграции и совместимость

SQL-миграции не добавлялись. Используются существующие таблицы `workspace_categories`, `workspace_universes`, `workspace_stories` и `workspace_character_story_links`. Системный Velvet Anatomy не меняет существующее поведение.

### Проверки

- contract test нормативного ТЗ;
- contract test порядка router registration;
- PostgreSQL regression test workspace isolation;
- category/universe/story filters;
- запрет cross-workspace story id;
- полный CI после открытия PR.

### PR и commit

Draft PR `#282` открыт из ветки `agent/workspace-requirements-and-taxonomy-ui`. Финальный merge commit будет указан после зелёного CI.

### Незавершённое

- inline-редактор категории, вселенной и историй персонажа;
- комбинированные фильтры;
- workspace scope для references, publications и analytics UI;
- управление ролями команды;
- публичный workspace directory на новом domain.

### Следующий шаг

После стабилизации `/wcatalog` подключить workspace taxonomy непосредственно к редактированию карточки персонажа, сохранению медиа и референсам, затем перевести публичный каталог.
