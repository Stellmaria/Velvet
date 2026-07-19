# Сессия: идемпотентное удаление архивных сообщений и P3D multi-story cleanup

- Дата: 2026-07-20
- ID: `2026-07-20-archive-delete-p3d-multi-story`
- Линия/фаза: Velvet Archive, hotfix + P3D
- Статус: `завершено`
- Ветка: `agent/archive-delete-p3d-multi-story`
- Базовый commit: `130ec0ab58d1773a897352fefc7bfc515ce53d1a`

## Перед началом

### Цель

Не считать ошибкой повторное удаление уже отсутствующего Telegram-сообщения архивной ветки и выполнить следующий P3D-срез для `stories/multi_story_kr.py`.

### Исходный контекст

При удалении медиа запись базы успешно удаляется, но Telegram может вернуть `Bad Request: message to delete not found`, если сообщение ветки уже отсутствует. Текущий код пишет WARNING и отправляет ошибку в аудит, хотя целевое состояние уже достигнуто. Одновременно `multi_story_kr.py` всё ещё импортирует `handlers.admin_directory`, `handlers.admin_stories` и приватные profile helpers.

### Планируемый объём

- добавить общий идемпотентный helper удаления Telegram-сообщений;
- считать `message to delete not found` состоянием `already_absent`, без WARNING и error-аудита;
- сохранить предупреждение и error-аудит для остальных Telegram API ошибок;
- применить helper в owner archive и public manager delete flows;
- вынести `AdminStoryCallback` в публичный story contract;
- перевести `multi_story_kr.py` на character/story contracts и public profile views;
- обновить legacy consumer inventory и regression tests;
- не менять callback prefixes, команды, SQL и пользовательские тексты.

### Критерии готовности

- повторное удаление отсутствующего сообщения не создаёт WARNING/Error Center запись;
- настоящие Telegram API ошибки продолжают логироваться;
- `multi_story_kr.py` не импортирует `velvet_bot.handlers`;
- callback prefixes `adir` и `astory` сохраняются;
- tests, Docker build и project notes contract зелёные.

### Риски и ограничения

Удаление записи из базы уже происходит до Telegram cleanup, поэтому Telegram delete должен быть идемпотентным и не откатывать успешную доменную операцию. Этот срез не удаляет handler aliases, пока у них остаются другие consumers.

## После завершения

### Фактически сделано

- добавлен общий `delete_message_idempotently` для Telegram delete operations;
- `Bad Request: message to delete not found` возвращает состояние `already_absent` и не создаёт WARNING/Error Center запись;
- остальные `TelegramBadRequest` и `TelegramAPIError` не подавляются и продолжают попадать в текущий error/audit flow;
- owner archive media browser и public archive manager используют один deletion helper;
- удалён logger filter, который маскировал любые ошибки удаления как шум;
- `AdminStoryCallback` и callback builder вынесены в `stories/contracts.py`;
- `stories/management.py` сохраняет compatibility export старого callback class;
- `stories/multi_story_kr.py` переведён на character/story contracts и public profile views;
- `characters/kr_profile_overrides.py` больше не импортирует callback contract из controller implementation;
- legacy consumer baseline уменьшен до 19 файлов, 28 references и 17 legacy modules;
- добавлены regression tests для идемпотентного удаления, настоящих Telegram ошибок и callback identity.

### Миграции и совместимость

Миграции не требуются. Callback prefixes `adir` и `astory`, callback payload fields, команды, SQL и пользовательские тексты не изменены. Старые `handlers.admin_stories` и другие aliases остаются доступными для tests и внешних imports.

### Проверки

- целевой regression suite: 34 tests, success;
- `compileall`, legacy inventory `--check` и `git diff --check`: success;
- полный локальный suite: 944 tests, success; 24 PostgreSQL integration tests skipped без `TEST_DATABASE_URL`;
- финальные GitHub Actions фиксируются на head PR #221.

### PR и commit

- PR: #221 `Fix archive topic deletion and clean multi-story imports`;
- ветка: `agent/archive-delete-p3d-multi-story`;
- production commit будет создан после полного локального прогона.

### Незавершённое

Остаются 19 production consumers, 28 legacy references, 17 legacy modules, 68 handler aliases и 8 runtime compatibility components. Идемпотентный helper пока применяется к двум архивным delete flows; остальные прямые delete operations следует классифицировать отдельным inventory, а не менять вслепую.

### Следующий шаг

Очистить следующую связанную consumer-группу: archive/reference parsing imports и публичные callback contracts, затем пересчитать baseline и удалить aliases только при нулевом consumer count.
