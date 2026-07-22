# Workspace-aware publication workflow and queues

- Дата: 2026-07-22
- ID: workspace-publication-queues
- Линия/фаза: Workspace product / publications isolation
- Статус: завершено
- Ветка: `agent/workspace-publication-queues`
- Базовый commit: `fce55fda561c10ccba2c8fc13bb91abab1c4b290`

## Перед началом

### Цель

Продолжить каноническое ТЗ `docs/requirements/workspace_product.md` и перевести публикационные черновики, проверку, расписание и worker очереди на workspace boundary.

### Исходный контекст

Персонажи, медиа и референсы уже были изолированы по workspace. Публикационный pipeline оставался глобальным: inbox, drafts, items и events не содержали workspace ID; Telegram UI использовал общий набор каналов; validation искал хэштеги только в системных `character_aliases`; очередь worker обрабатывала глобальные ID без явной tenant-границы.

### Планируемый объём

- добавить workspace ID во все публикационные таблицы;
- закрепить item/event за draft составным внешним ключом;
- изолировать inbox, черновики, списки и изменения по workspace;
- сохранить общую командную очередь внутри одного workspace;
- перевести validation на workspace aliases и `requires_story` из taxonomy;
- получать канал публикации и timezone из настроек активного пространства;
- добавить personal-workspace Telegram router перед legacy-центром;
- разрешить guarded workspace routes через global owner middleware;
- сохранить системный workspace и общий worker;
- добавить contract и PostgreSQL regression tests.

### Критерии готовности

- одинаковый source message можно сохранить в разных workspace;
- чужой draft ID нельзя прочитать, изменить, отменить или опубликовать;
- team editors видят общую очередь своего workspace;
- duplicate detection не пересекает соседние workspace;
- хэштеги разрешаются только через aliases активного workspace;
- обязательность истории определяется `workspace_universes.requires_story`;
- очередь публикует в `workspace_channels(kind='publication')`;
- расписание отображается в timezone пространства;
- worker обрабатывает due drafts всех workspace без снятия tenant-проверок на mutation;
- system workspace `1` сохраняет прежний интерфейс;
- tests, type-check, Docker build, notes contract и restore drill зелёные.

### Риски и ограничения

- один workspace использует один подключённый publication channel;
- роли reviewer/viewer не получают права менять публикации, минимальная роль центра — editor;
- channel post history пока остаётся привязанной к физическому Telegram channel ID, что достаточно для проверки опубликованных дублей;
- personal router переиспользует канонические UI-компоненты legacy-центра, чтобы не создавать второй несовместимый дизайн;
- миграция обязательна и должна пройти dump/restore drill.

## После завершения

### Фактически сделано

- миграция `907_workspace_publications.sql` добавляет `workspace_id` в inbox, drafts, items и events;
- существующие публикационные данные backfill-ятся в system workspace `1`;
- item/event защищены составными FK `(workspace_id, draft_id)`;
- inbox uniqueness включает workspace;
- PublicationRepository, DraftRepository, services, actions и facades получили workspace scope;
- personal workspace использует общую командную очередь независимо от автора конкретного черновика;
- system workspace сохраняет старое owner filtering;
- validation использует `workspace_character_aliases`, primary story links и `workspace_universes.requires_story`;
- duplicate draft detection ограничен workspace;
- scheduled worker использует внутренний cross-workspace lookup только для выбора due draft, а все state mutations выполняет с найденным workspace ID;
- `PublicationWorkspaceContext` разрешает активный workspace, роль, module, channel и timezone;
- personal publication router перехватывает команды, callbacks, schedule/text replies и inbox capture до legacy-центра;
- global owner middleware пропускает только перечисленные guarded workspace routes и затем полагается на повторную проверку handler-а;
- системный Velvet Anatomy продолжает использовать legacy publication center.

### Миграции и совместимость

Добавлена миграция `907_workspace_publications.sql`.

Старые вызовы без workspace ID продолжают использовать `DEFAULT_WORKSPACE_ID = 1`. Общий publication worker сохранён и безопасно обрабатывает due queues всех пространств.

### Проверки

Добавлены contract и PostgreSQL regression tests на:

- наличие workspace columns и составных FK;
- workspace-aware APIs;
- порядок personal router перед legacy center;
- guarded access middleware;
- одинаковый source message в двух workspace;
- запрет foreign read/cancel;
- общую team queue внутри workspace;
- отсутствие cross-workspace duplicate draft;
- alias resolution внутри workspace;
- блокировку forged event;
- внутреннюю загрузку due draft worker-ом с сохранением target channel.

Первый полный CI подтвердил все новые PostgreSQL-сценарии. После восстановления system-workspace SQL-контрактов и явного legacy fallback запущен финальный прогон.

### PR и commit

PR: `#286 Isolate publication workflows by workspace`. Финальный merge commit фиксируется после зелёного CI.

### Незавершённое

- workspace-aware analytics;
- Telegram UI управления ролями team;
- расширенный выбор нескольких publication channels внутри одного workspace, если будет утверждён отдельным требованием.

### Следующий шаг

Перевести analytics dashboards, channel/discussion statistics и management views на active workspace и его подключённые каналы.
