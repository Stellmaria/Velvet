# Сессия: защита публичного репозитория

- Дата: 2026-07-19
- ID: `2026-07-19-public-repository-security-hardening`
- Линия/фаза: Velvet Archive, эксплуатационная стабилизация
- Статус: `частично`
- Ветка: `agent/public-repo-security-hardening`
- Базовый commit: `7864290ff67866c12073579dad6884952f4753f5`
- PR: `#196`

## Перед началом

### Цель

Проверить публичную поверхность репозитория после смены visibility на public и удалить из текущего дерева персональные Telegram defaults, не меняя бизнес-поведение владельца, модератора, аналитики и Supervisor.

### Исходный контекст

GitHub Actions для private repository исчерпал включённые 2000 минут. После перевода репозитория в public обязательные tests, Docker build и project notes contract снова выполняются и PR #195 был проверен и слит. Публичный аудит текущего дерева не обнаружил tracked `.env`, логов, дампов, присланных JSON, GitHub PAT, OpenAI key, private key или Telegram bot token. При этом обнаружены реальные Telegram username/ID в `.env.example`, README и production defaults, а moderator ID напрямую встроен в access policy.

### Какую существующую функцию улучшает изменение

Изменение повышает безопасность эксплуатации существующего owner-oriented Telegram-бота и делает конфигурацию переносимой: owner/moderator/log/analytics identities будут задаваться только окружением, а не исходным кодом.

### Что станет надёжнее и понятнее

- публикация исходников больше не раскрывает текущие персональные defaults в активной конфигурации;
- новый оператор не запустит копию бота с чужими Telegram ID по умолчанию;
- moderator access, command menus, logs и analytics используют единый `Settings` boundary;
- CI будет блокировать возврат персональных значений и очевидных секретов в tracked configuration/docs.

### Почему это не новая предметная область

Изменение не добавляет пользовательских сценариев. Оно укрепляет существующие access/configuration/CI boundaries и относится к разрешённой эксплуатационной стабилизации.

### Планируемый объём

- добавить `moderator_user_ids` в `Settings` и переменную `MODERATOR_USER_IDS`;
- убрать реальный username, moderator ID, log chat ID и analytics channel ID из production defaults и `.env.example`;
- перевести middleware, command menus и startup logging на `settings.moderator_user_ids`;
- обезличить README и актуальную документацию, не редактируя применённые SQL-миграции;
- добавить public-repository safety inventory/test для placeholders и запрещённых credential patterns;
- выполнить полный tests, Docker build и project notes contract.

### Критерии готовности

- текущий production-код не содержит реальных owner/moderator/log/analytics defaults;
- `.env.example` содержит только placeholders или пустые optional values;
- moderator access продолжает работать через `MODERATOR_USER_IDS`;
- tracked `.env`, dumps, logs и известные credential patterns блокируются тестом;
- все обязательные CI checks зелёные;
- исторические миграции не изменены.

### Риски и ограничения

Telegram ID и username уже присутствуют в Git history и применённых migrations. Обычный PR удалит их из текущего дерева, но не из истории. Полное удаление из истории требует отдельного destructive history rewrite с ротацией веток/forks и не выполняется в этом срезе. Telegram IDs не являются токенами доступа, однако остаются персональными идентификаторами.

## После завершения

Заполняется после удаления временного workflow и полного CI.