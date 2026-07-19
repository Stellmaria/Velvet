# Сессия: защита публичного репозитория

- Дата: 2026-07-19
- ID: `2026-07-19-public-repository-security-hardening`
- Линия/фаза: Velvet Archive, эксплуатационная стабилизация
- Статус: `завершено`
- Ветка: `agent/public-repo-security-hardening`
- Базовый commit: `7864290ff67866c12073579dad6884952f4753f5`
- PR: `#196`

## Перед началом

### Цель

Проверить публичную поверхность репозитория после смены visibility на public и удалить из текущего дерева персональные Telegram defaults, не меняя бизнес-поведение владельца, модератора, аналитики и Supervisor.

### Исходный контекст

GitHub Actions для private repository исчерпал включённые 2000 минут. После перевода репозитория в public обязательные tests, Docker build и project notes contract снова выполняются и PR #195 был проверен и слит. Публичный аудит текущего дерева не обнаружил tracked `.env`, логов, дампов, присланных JSON, GitHub PAT, OpenAI key, private key или Telegram bot token. При этом обнаружены реальные Telegram username/ID в `.env.example`, README и production defaults, а moderator ID напрямую встроен в access policy.

### Какую существующую функцию улучшает изменение

Изменение повышает безопасность эксплуатации существующего owner-oriented Telegram-бота и делает конфигурацию переносимой: owner/moderator/log/analytics identities задаются только окружением, а не исходным кодом.

### Что стало надёжнее и понятнее

- публикация исходников больше не раскрывает текущие персональные defaults в активной конфигурации;
- новый оператор не запустит копию бота с чужими Telegram ID по умолчанию;
- moderator access, command menus, logs и analytics используют единый `Settings` boundary;
- CI блокирует возврат персональных значений, runtime-дампов и очевидных секретов в tracked configuration/docs.

### Почему это не новая предметная область

Изменение не добавляет пользовательских сценариев. Оно укрепляет существующие access/configuration/CI boundaries и относится к разрешённой эксплуатационной стабилизации.

### Планируемый объём

- добавить `moderator_user_ids` в `Settings` и переменную `MODERATOR_USER_IDS`;
- убрать реальный username, moderator ID, log chat ID и analytics channel ID из production defaults и `.env.example`;
- перевести middleware, command menus и startup logging на `settings.moderator_user_ids`;
- обезличить README и актуальную документацию, не редактируя применённые SQL-миграции;
- добавить public-repository safety test для placeholders и запрещённых credential patterns;
- выполнить полный tests, Docker build и project notes contract.

### Критерии готовности

- текущий production-код не содержит реальных owner/moderator/log/analytics defaults;
- `.env.example` содержит только placeholders или пустые optional values;
- moderator access продолжает работать через `MODERATOR_USER_IDS`;
- tracked `.env`, dumps, logs и известные credential patterns блокируются тестом;
- все обязательные CI checks зелёные;
- исторические миграции не изменены.

### Риски и ограничения

Telegram ID и username уже присутствуют в Git history и применённых migrations. Обычный PR удаляет их из текущего дерева, но не из истории. Полное удаление из истории требует отдельного destructive history rewrite с ротацией веток/forks и не выполняется в этом срезе. Telegram IDs не являются токенами доступа, однако остаются персональными идентификаторами.

## После завершения

### Фактически сделано

- подтверждено, что `Stellmaria/Velvet` имеет public visibility и стандартные GitHub-hosted runners снова выполняют jobs;
- PR #195 повторно проверен после смены visibility и слит в `main`;
- `Settings` расширен полем `moderator_user_ids`, добавлена переменная окружения `MODERATOR_USER_IDS`;
- owner username, moderator ID, log chat ID и analytics channel ID удалены из active defaults;
- access middleware, dispatcher, command menus и startup logging переведены на configuration-driven moderator identities;
- публичная кнопка скачивания и download boundary больше не зависят от конкретного Telegram ID;
- `.env.example`, README, инструкции импорта и публикации обезличены;
- CLI импорта Telegram требует явные `--chat-id` и `--parent-channel-id`, а не использует чужие defaults;
- access/config tests используют нейтральные fixtures;
- добавлен `tests/test_public_repository_safety.py`, запрещающий tracked `.env`, dumps, databases, runtime outputs, известные credential patterns и возврат персональных defaults;
- safety policy разрешает только явные служебные placeholders и штатный `data/story_catalog.json`;
- временные patch workflows и диагностический файл полностью удалены из итогового diff;
- применённые SQL migrations не редактировались.

### Миграции и совместимость

Миграции PostgreSQL не требуются и не изменялись. В рабочем `.env` необходимо сохранить существующие реальные значения `ALLOWED_USER_IDS`, `MODERATOR_USER_IDS`, `LOG_CHAT_ID` и `ANALYTICS_CHANNEL_IDS`. Старые compatibility exports `CHARACTER_EDITOR_USER_IDS` и `MODERATOR_USER_IDS` остаются пустыми наборами; runtime access получает фактические ID через `Settings` и `AccessPolicy`. Команды, callback prefixes и owner/moderator/public role boundaries сохранены.

### Проверки

- публичный поиск не обнаружил GitHub PAT, OpenAI API key, private key или Telegram bot token;
- tracked `.env`, `result.json`, логи, backups и database dumps в текущем дереве не обнаружены;
- Docker build #499: success;
- tests #963 выполнил 849 тестов: все code, PostgreSQL, access и security checks прошли; единственным падением был незавершённый worklog, исправленный этим commit;
- P2 inventory восстановлен на `67 approved / 0 unresolved`, callback inventory не изменён;
- финальные обязательные checks выполняются на завершённой документационной записи и являются merge gate PR #196.

### PR и commit

- PR: #196 `Harden public repository configuration`;
- ветка: `agent/public-repo-security-hardening`;
- базовый commit: `7864290ff67866c12073579dad6884952f4753f5`;
- постоянный safety contract: `tests/test_public_repository_safety.py`.

### Незавершённое

Активное дерево обезличено, но реальные Telegram identifiers остаются доступными в старых commits и применённых migrations. Это не секреты доступа. Их полное удаление возможно только отдельным destructive history rewrite, который потребует force-push, обновления всех клонов и учёта существующих forks. Branch protection и GitHub Secret Scanning settings должны контролироваться в интерфейсе репозитория, поскольку подключённый GitHub integration не предоставляет write/read actions для этих настроек.

### Следующий шаг

После зелёного финального CI слить PR #196. Затем продолжить P3C перенос characters/stories presentation controllers отдельным небольшим срезом.