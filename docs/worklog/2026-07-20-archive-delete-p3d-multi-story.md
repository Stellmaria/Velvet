# Сессия: идемпотентное удаление архивных сообщений и P3D multi-story cleanup

- Дата: 2026-07-20
- ID: `2026-07-20-archive-delete-p3d-multi-story`
- Линия/фаза: Velvet Archive, hotfix + P3D
- Статус: `в работе`
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
