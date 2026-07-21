# Сессия: Workspace archive isolation

- Дата: 2026-07-21
- ID: `2026-07-21-workspace-archive-isolation`
- Линия/фаза: multi-workspace archive isolation
- Статус: `завершено`
- Ветка: `agent/workspace-archive-isolation`
- Базовый commit: `157ddb7dcfd1513455649eea5bdfe81eb3c413b3`

## Перед началом

### Цель

Продолжить multi-workspace реализацию после PR #275: изолировать приватный и публичный архив по `workspace_id`, добавить безопасный выбор активного пространства и подготовить базовый мастер подключения пользовательских Telegram-каналов.

### Исходный контекст

Workspace foundation уже хранит пространства, участников, настройки и каналы, а персонажи ограничены `workspace_id`. Архивные, публичные и Telegram application boundaries всё ещё использовали только `character_id` либо глобальные настройки, поэтому внешний пользовательский интерфейс был намеренно отключён.

### Планируемый объём

- workspace scope для archive repository/service;
- workspace scope для public archive repository/service;
- проверка принадлежности персонажа до чтения и изменения медиа;
- активное пространство пользователя без доступа к чужим workspace;
- базовый channel connection service с проверкой роли владельца/администратора;
- regression и PostgreSQL isolation tests;
- сохранение текущего Velvet поведения через workspace `1` по умолчанию.

### Критерии готовности

- пользователь не может открыть архив персонажа другого workspace по известному `character_id`;
- public archive выдаёт категории, персонажей и медиа только активного workspace;
- owner/admin может менять каналы только своего workspace;
- текущие команды Стэл продолжают работать без изменения интерфейса;
- tests, restore drill, type-check, Docker и project notes зелёные.

### Риски и ограничения

Эта фаза не должна включать внешний интерфейс раньше завершения всех read/write guards. References, publications, Qwen и analytics остаются отдельными следующими срезами, но архивные маршруты не должны иметь обхода через прямой ID.

## После завершения

### Фактически сделано

- добавлена миграция `902_workspace_active_selection.sql` с сохранением активного пространства пользователя;
- `WorkspaceService` умеет безопасно выбирать и восстанавливать active workspace только среди доступных пользователю пространств;
- создание личного workspace сразу делает его активным для владельца;
- удаление участника очищает устаревший active workspace;
- один Telegram `chat_id` нельзя привязать к двум разным workspace: repository использует transaction advisory lock и проверку конфликта;
- `ArchiveRepository` ограничивает просмотр, prompt, spoiler, public/adult flags и удаление по `workspace_id`;
- `PublicArchiveRepository` ограничивает media state, views, downloads, likes, subscriptions и notification deliveries по `workspace_id`;
- публичный каталог историй считает только персонажей выбранного пространства;
- `build_archive_service` и `build_public_archive_service` принимают workspace context, сохраняя ID `1` по умолчанию;
- добавлены PostgreSQL-тесты на прямой чужой `character_id`, попытку чужой mutation, запись чужого view, выбор чужого workspace, конфликт Telegram-чата и workspace-scoped directory;
- generated repository layout и Telegram navigation inventories регенерированы.

### Миграции и совместимость

Новая миграция: `902_workspace_active_selection.sql`. Она добавляет только таблицу пользовательских предпочтений и индекс, не меняя существующие архивные данные. Текущий Velvet продолжает работать в системном workspace ID `1` без изменения команд и интерфейса. External workspace UI в этой фазе не включён.

### Проверки

Проверенный implementation head `597e5bc9508b4fa2d133fe52fbbdf443dc82086c`:

- tests run `1416`: **1040 tests выполнены**, все предметные и PostgreSQL isolation tests прошли; три служебных падения относились только к незавершённому worklog и устаревшим generated inventories;
- backup restore drill run `167`: **success**;
- type check run `69`: **success**;
- Docker build run `864`: **success**.

Generated inventories обновлены commit `73e3d008d2cdfed9716d45ef01785e5646db7114`. Финальный обычный commit запускает повторный полный CI, включая project notes contract.

### PR и commit

PR #276: `Isolate archive and public activity by workspace`.

### Незавершённое

- внешний Telegram-интерфейс создания и переключения пространств ещё не включён;
- референсы, публикации, Qwen, subscriptions delivery orchestration и analytics требуют отдельных workspace-срезов;
- мастер подключения каналов пока представлен безопасным domain/service contract, без пошагового Telegram UI и проверки фактических admin rights через Bot API.

### Следующий шаг

Перевести references и publication boundaries на active workspace, затем добавить Telegram-меню `Моё пространство`, создание архива, переключение workspace и мастер проверки прав бота в каналах.
