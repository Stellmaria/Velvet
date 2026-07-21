# Сессия: Workspace character taxonomy

- Дата: 2026-07-21
- ID: `2026-07-21-workspace-character-taxonomy`
- Линия/фаза: multi-workspace characters
- Статус: `частично`
- Ветка: `agent/workspace-character-taxonomy`
- Базовый commit: `036b4fee4088afada593670ed25707048ad3ac2f`

## Перед началом

### Цель

Продолжить личные пространства после PR #277: превратить кнопку «Персонажи» из справочной заглушки в рабочий раздел, связать личные карточки с `workspace_categories`, `workspace_universes` и `workspace_stories`, поддержать несколько историй одного персонажа и сохранить системный Velvet без изменения старых команд.

### Исходный контекст

Workspace foundation уже изолировал персонажей по `workspace_id`, а личная taxonomy хранилась отдельно. Старые character-management экраны продолжали использовать системные константы, поэтому пользователь мог создать категории, вселенные и истории, но не мог назначить их персонажу своего архива.

### Планируемый объём

- рабочий вход через модуль «Персонажи»;
- создание и список персонажей активного личного пространства;
- карточка с категорией, вселенной и историями;
- назначение workspace category и universe;
- несколько workspace stories у одного персонажа;
- очистка несовместимых историй при смене вселенной;
- PostgreSQL isolation tests;
- отсутствие изменений в системном Velvet workspace `1`.

### Критерии готовности

- прямой ID персонажа другого пространства не изменяется;
- категория и вселенная выбираются только из taxonomy текущего workspace;
- история другого workspace не назначается;
- первая история становится основной, остальные остаются дополнительными;
- смена вселенной очищает старые истории;
- внешний владелец работает внутри middleware-approved workspace FSM;
- старые `/create`, `/characters`, story и archive handlers Velvet не меняются.

### Риски и ограничения

- нельзя смешивать legacy `character_stories` системного Velvet и новые `workspace_stories` личных архивов;
- прямые связи должны быть защищены не только application checks, но и внешними ключами PostgreSQL;
- Telegram callback модуля `characters` должен перехватываться раньше общей справочной заглушки;
- этот срез не переводит системный workspace `1` на новый пользовательский интерфейс;
- переименование, удаление, aliases, prompt URL, topic binding и публичный каталог остаются отдельными следующими срезами.

## После завершения

### Фактически сделано

- существующая кнопка модуля `characters` перехватывается до справочной заглушки;
- открывается отдельная FSM-сессия управления персонажами личного архива;
- добавлены действия: создание, список, карточка, категория, вселенная, история и просмотр структуры;
- все действия повторно проверяют membership, роль владельца и включённый модуль;
- создание использует `Database.create_character(..., workspace_id=...)`;
- категории и вселенные проверяются по включённым записям текущего workspace;
- добавлена таблица `workspace_character_story_links`;
- одному персонажу можно назначить несколько workspace stories;
- первая назначенная история помечается основной;
- удаление основной истории автоматически выбирает следующую;
- смена вселенной очищает старые workspace story links;
- составные внешние ключи PostgreSQL запрещают связать персонажа и историю разных workspace;
- системный Velvet не переводится на новый экран и продолжает использовать существующий контур;
- integrity scanner дополнен учётом команд, зарегистрированных через `router.message.register`.

### Миграции и совместимость

Добавлена миграция `904_workspace_character_taxonomy.sql`. Она создаёт `workspace_character_story_links`, индексы для workspace-scoped выборок и ограничение одного primary story на персонажа. Составные внешние ключи используют пары `(workspace_id, id)` и не позволяют создать cross-workspace связь даже прямым SQL.

Существующие `character_story_links` и `character_stories` не изменяются. Системный Velvet Anatomy продолжает работать через прежний story-контур, поэтому текущие карточки, команды и публикации workspace `1` сохраняют совместимость.

### Проверки

Добавлены contract и PostgreSQL regression tests на:

- создание личного персонажа в выбранном workspace;
- назначение собственной категории и вселенной;
- добавление и удаление workspace story;
- запрет назначения истории другого workspace;
- очистку историй при смене вселенной;
- структуру новой миграции.

Первый CI-срез подтвердил успешные type-check и Docker build. `project notes contract` обнаружил неполную структуру этой записи; обязательные разделы добавлены данным исправлением. Полные tests, restore drill и повторный notes contract проверяются на обновлённом head PR.

### PR и commit

Draft PR #278: `Wire personal workspace character taxonomy`.

Базовый commit: `036b4fee4088afada593670ed25707048ad3ac2f`. Финальный implementation head определяется последним commit ветки `agent/workspace-character-taxonomy` после исправлений CI.

### Незавершённое

- переименование и удаление персонажа личного workspace;
- aliases и хэштеги личного персонажа;
- prompt URL и Telegram topic binding;
- inline-кнопки выбора категорий, вселенных и историй вместо текстовых действий FSM;
- роли admin/editor для character-management вместо текущего owner-only среза;
- перевод private/public directory builders на `workspace_character_story_links`;
- отображение собственных workspace stories в публичном каталоге.

### Следующий шаг

Добавить rename/delete/topic/prompt и aliases для личного персонажа, затем перевести private/public directory builders на workspace taxonomy и `workspace_character_story_links`.
