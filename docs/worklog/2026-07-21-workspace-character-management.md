# Сессия: Workspace character management

- Дата: 2026-07-21
- ID: `2026-07-21-workspace-character-management`
- Линия/фаза: multi-workspace character management
- Статус: `частично`
- Ветка: `agent/workspace-character-management`
- Базовый commit: `a4666d4a455d606cfbc4f206cdace2cb1628d10d`

## Перед началом

### Цель

Продолжить multi-workspace персонажей после PR #278: добавить безопасное переименование и удаление с подтверждением, workspace-scoped aliases, ссылку на промт и Telegram-тему, не изменяя существующий системный контур Velvet Anatomy.

### Исходный контекст

Личный workspace уже поддерживал создание, просмотр, категории, вселенные и несколько историй. Расширенное управление оставалось только в legacy-командах системного Velvet, а таблица `character_aliases` имела глобальную уникальность и не подходила для независимых личных архивов.

### Планируемый объём

- отдельный router расширенного управления личными персонажами;
- переименование в границах текущего workspace;
- удаление только после совпадающего подтверждения;
- отдельные алиасы с уникальностью внутри workspace;
- установка и удаление ссылки на промт;
- проверка и назначение Telegram forum topic;
- поддержка ролей editor для изменений и admin для удаления;
- PostgreSQL regression tests;
- отсутствие изменения поведения системного workspace `1`.

### Критерии готовности

- ID персонажа другого workspace нельзя переименовать, удалить или изменить;
- одинаковый алиас допустим в разных пространствах, но не у разных персонажей одного;
- имя персонажа синхронизируется с его name-alias;
- удаление без предварительного подтверждения невозможно на уровне UI;
- prompt URL проходит существующую Telegram-валидацию;
- Telegram-тема проверяется ботом до записи;
- удаление персонажа каскадно очищает workspace aliases и story links;
- новый router зарегистрирован раньше legacy workspace-admin;
- системный Velvet продолжает использовать прежние команды и таблицу aliases.

### Риски и ограничения

Legacy `character_aliases` и аналитические hashtag triggers остаются системным контуром. Личные алиасы намеренно изолированы в отдельной таблице и пока не участвуют в аналитике системного Telegram-канала. Полноценные inline-кнопки и публичный каталог личного архива остаются отдельными срезами.

## После завершения

### Фактически сделано

- добавлен `domains/workspaces/character_management.py` с workspace-scoped persistence;
- добавлен отдельный Telegram router для расширенного управления;
- реализованы создание, карточка, список и прежняя классификация через новый сервис;
- добавлены rename и delete с двухшаговым подтверждением;
- добавлены ручные aliases и запрет удаления name-alias;
- добавлены prompt URL и Telegram topic set/remove;
- editor может изменять карточки, admin требуется для удаления;
- системный workspace блокируется новым router и остаётся на legacy UI;
- добавлены изоляционные и регрессионные тесты PostgreSQL.

### Миграции и совместимость

`905_workspace_character_management.sql` создаёт `workspace_character_aliases`, композитный FK на `(workspace_id, character_id)`, уникальность алиаса внутри workspace и backfill name-aliases. Старые таблицы и handlers системного Velvet не изменяются.

### Проверки

Планируются project integrity, PostgreSQL integration tests, type-check, Docker build, backup restore drill и project notes contract в GitHub Actions.

### PR и commit

Будет создан draft PR из ветки `agent/workspace-character-management` в `main`. Финальные SHA и номер PR фиксируются в GitHub.

### Незавершённое

- inline-кнопки для выбора действий, категорий, вселенных и историй;
- перенос private/public directory builders на workspace taxonomy;
- управление участниками и доступ к экрану для editor/admin из workspace home;
- workspace aliases пока не участвуют в системной hashtag-аналитике.

### Следующий шаг

Перевести приватный и публичный каталоги личного workspace на `workspace_character_story_links`, добавить inline-навигацию карточек и затем открыть управление ролями команды из интерфейса пространства.
