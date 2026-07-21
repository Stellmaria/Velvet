# Сессия: Workspace foundation

- Дата: 2026-07-21
- ID: `2026-07-21-workspace-foundation`
- Линия/фаза: multi-workspace foundation
- Статус: `частично`
- Ветка: `agent/workspace-foundation`
- Базовый commit: `3b38844fd57cb4ff18e3c8de5710facdef394e69`

## Перед началом

### Цель

Заложить безопасный фундамент для отдельных пользовательских архивов без пересечения с пространством Стэл: рабочие пространства, роли участников, настройки Telegram-каналов и изоляция персонажей по `workspace_id`.

### Исходный контекст

Текущая модель была однопользовательской. Персонажи имели глобально уникальный `normalized_name`, каналы загружались из глобального `.env`, а роли owner/moderator не были привязаны к отдельному архиву. Простое добавление нового user ID не создавало изоляцию данных.

### Планируемый объём

- миграция `workspaces`, `workspace_members`, `workspace_settings`, `workspace_channels`;
- создание системного пространства Velvet и перенос существующих персонажей в него;
- добавление `workspace_id` в `characters`;
- уникальность имени персонажа внутри workspace;
- domain models/repository/service для workspace;
- безопасный resolver пространства пользователя;
- тесты миграции, ролей, настроек и недоступности чужого workspace;
- контракт следующей фазы для перевода archive queries на обязательный workspace context.

### Критерии готовности

- существующие данные автоматически принадлежат системному workspace;
- один и тот же персонаж может существовать в разных пространствах;
- пользователь получает только workspace, участником которого является;
- роли ограничены `owner/admin/editor/reviewer/viewer`;
- Telegram chat IDs и ссылки хранятся отдельно для каждого пространства;
- схема не открывает доступ к owner-only Supervisor/GitHub/Codex;
- полный CI зелёный.

### Риски и ограничения

Это первая фаза. Она создаёт tenant boundary и переносит ownership персонажей, но не включает внешнему пользователю production-меню до завершения сквозного перевода archive/publication/Qwen запросов на `workspace_id`. Такой порядок намеренно консервативен: сначала изоляция, потом кнопки.

## После завершения

### Фактически сделано

- добавлены `workspaces`, `workspace_members`, `workspace_settings` и `workspace_channels`;
- системное пространство Velvet закреплено за ID `1`;
- существующие персонажи мигрируют в системное пространство;
- глобальная уникальность имени заменена на `UNIQUE (workspace_id, normalized_name)`;
- `Database.create_character`, поиск, topic binding и списки получили совместимый `workspace_id=1` по умолчанию;
- `CharacterDirectoryRepository` фильтрует чтение и изменение по workspace;
- добавлены роли `owner/admin/editor/reviewer/viewer` и явный global-owner support bypass;
- настройки каналов, публичного архива, скачиваний, Qwen и часового пояса хранятся отдельно;
- добавлены unit и PostgreSQL isolation tests;
- generated repository-layout и Telegram navigation inventories обновлены.

### Миграции и совместимость

Новая миграция: `901_workspaces.sql`. Номер выбран автоматически из фактического каталога после обнаружения существующих `102_media_set_consistency.sql` и `103_qwen_quality_calibration.sql`. Старые вызовы без workspace продолжают работать в системном пространстве ID `1`. Существующие персонажи, медиа и topic links сохраняются. Внешний пользовательский интерфейс пока не включён, поэтому частично переведённые домены не могут быть использованы для обхода tenant boundary.

### Проверки

Проверенный implementation head `ae660fc4248cc62003c9f3f86a94446d25ef928a`:

- tests run `1413`: **1033 tests, success**;
- backup restore drill run `164`: **success**, реальный custom-format dump восстановлен в свежую PostgreSQL-базу;
- type check run `66`: **success**;
- Docker build run `861`: **success**;
- project notes contract run `735`: **success**.

Отдельные PostgreSQL-тесты подтвердили одинаковое имя персонажа в двух пространствах и невозможность открыть чужого персонажа через workspace-scoped directory.

### PR и commit

PR #275: `Add workspace foundation for isolated personal archives`. Проверенный implementation head: `ae660fc4248cc62003c9f3f86a94446d25ef928a`.

### Незавершённое

- archive/public archive, stories, references, publication, Qwen, subscriptions и analytics ещё не переведены сквозным образом на workspace context;
- мастер подключения каналов и внешнее меню не включены;
- active workspace selection в Telegram FSM не добавлен.

### Следующий шаг

Перевести archive/public archive read/write boundaries на обязательный workspace context, затем добавить выбор активного пространства и мастер проверки прав бота в пользовательских каналах.
