# Workspace-aware analytics and discussion dashboards

- Дата: 2026-07-22
- ID: workspace-analytics
- Линия/фаза: Workspace product / analytics isolation
- Статус: завершено
- Ветка: `agent/workspace-analytics`
- Базовый commit: `2f72a0e6c0e54e5356753e8105c84020009e4e4e`

## Перед началом

### Цель

Продолжить каноническое ТЗ `docs/requirements/workspace_product.md` и подключить channel/discussion analytics к активному workspace без смешивания статистики соседних архивов.

### Исходный контекст

Channel analytics хранилась по физическому Telegram `channel_id`, live ingestion слушал только глобальный список каналов, dashboard использовал system aliases, а discussion sources выбирались из общего `tracked_channels`. Личные workspace уже имели собственные characters, taxonomy, media, references и publication queues, но analytics module фактически оставался системным.

### Планируемый объём

- установить жёсткое правило принадлежности Telegram-чата одному workspace;
- разрешить одному workspace использовать один чат сразу в нескольких ролях;
- получать analytics/publication/public и discussion channels из `workspace_channels`;
- проверять module `analytics` и минимальную роль reviewer;
- выполнять live ingestion личных каналов до legacy system handler;
- разрешать хэштеги через `workspace_character_aliases`;
- использовать primary story из workspace taxonomy в character statistics;
- добавить personal commands и dashboard callbacks;
- подключать discussion chat только с ролью editor;
- фильтровать discussion list до разрешённых chat ID;
- сохранить system analytics, global management и legacy SQL;
- добавить contract и PostgreSQL regression tests.

### Критерии готовности

- один Telegram chat ID нельзя подключить к двум workspace;
- один chat ID можно использовать как analytics/publication/public внутри одного workspace;
- выключенный analytics module не получает live ingestion;
- active workspace выбирает analytics channel раньше publication/public;
- одинаковые character aliases в разных workspace не смешиваются;
- `/analytics`, `/channelstats`, `/promptstats`, `/hashtagstats`, `/characterstats` используют активный workspace;
- `/trackdiscussion` требует editor и записывает чат в workspace;
- `/discussionstats` и `dash:discussion` отклоняют чужой chat ID;
- список обсуждений не показывает unowned tracked sources;
- system workspace сохраняет legacy dashboard и management overrides;
- tests, type-check, Docker build, notes contract и restore drill зелёные.

### Риски и ограничения

- raw channel analytics остаётся keyed по физическому Telegram chat ID; изоляция обеспечивается DB-trigger эксклюзивного владельца;
- существующий physical chat нельзя повторно назначить другому workspace, пока первая привязка не удалена;
- personal dashboard намеренно не открывает `dashm:` global management actions;
- исторические personal posts, сохранённые до подключения analytics module, не появляются автоматически без повторного импорта/получения update;
- Telegram export import остаётся system-only до отдельного tenant-aware импорта.

## После завершения

### Фактически сделано

- миграция `908_workspace_channel_ownership.sql` добавляет DB-trigger `enforce_workspace_channel_owner`;
- advisory transaction lock закрывает race при одновременной привязке chat ID;
- `AnalyticsWorkspaceContext` разрешает active workspace, reviewer role, module и channel priority;
- live ingest source определяется через `workspace_channels` и enabled analytics module;
- personal channel posts разрешают characters только через `workspace_character_aliases`;
- system ingestion остаётся в legacy `channel_analytics.ingest_channel_post`;
- character usage/dashboard использует workspace primary story с fallback на legacy story;
- personal analytics router зарегистрирован раньше всех legacy analytics controllers;
- команды channel/prompt/hashtag/character stats используют channel IDs активного workspace;
- dashboard `dash:` callbacks доступны personal workspace, `dashm:` остаётся global owner only;
- discussion callbacks повторно проверяют `workspace_channels(kind='discussion')`;
- discussion list предварительно фильтруется, поэтому чужие tracked sources не раскрываются;
- `/trackdiscussion` записывает workspace channel и tracked source;
- `/discussionstats` выбирает только discussion chat активного workspace;
- global owner access middleware пропускает guarded analytics routes и оставляет system management закрытым.

### Миграции и совместимость

Добавлена миграция `908_workspace_channel_ownership.sql`.

Исторические analytics tables не переписывались. Их tenant boundary теперь определяется эксклюзивным владельцем физического chat ID. System channels из `.env` продолжают работать без обязательной записи в `workspace_channels`.

### Проверки

Добавлены contract и PostgreSQL regression tests на:

- DB-trigger и advisory lock;
- порядок personal router перед legacy analytics;
- guarded `dash:` без открытия `dashm:`;
- workspace alias ingestion;
- workspace primary story в statistics;
- discussion ownership checks;
- несколько channel kinds внутри одного workspace;
- запрет одного chat ID в соседнем workspace;
- channel priority и scoped discussion list;
- disabled analytics module;
- одинаковый alias в соседних workspace.

### PR и commit

PR создаётся после завершения generated inventory. Финальный merge commit фиксируется после зелёного CI.

### Незавершённое

- Telegram UI управления team members и ролями;
- tenant-aware Telegram export import;
- отдельный analytics channel selector для workspace с несколькими физическими каналами, если будет утверждён продуктовый сценарий.

### Следующий шаг

Добавить owner/admin Telegram UI для списка участников workspace, приглашения по Telegram ID, смены ролей и удаления участника с защитой владельца.
