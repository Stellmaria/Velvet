# Сессия: SQL alias creation grant

- Дата: 2026-07-22
- ID: `2026-07-22-workspace-grant-sql-alias-hotfix`
- Линия/фаза: workspace administration hotfix
- Статус: `завершено`
- Ветка: `agent/workspace-grant-sql-hotfix`
- Базовый commit: `main`

## Перед началом

### Цель

Устранить падение панели Стэл с `PostgresSyntaxError` около ключевого слова `grant`.

### Исходный контекст

Методы `list_creation_grants` и `get_creation_grant` использовали зарезервированное PostgreSQL слово `grant` как SQL alias. Ошибка проявлялась отдельно через `fetch` и `fetchrow`, но имела одну корневую причину.

### Планируемый объём

- переименовать alias во всех запросах доменного сервиса;
- выполнить оба запроса на настоящем PostgreSQL;
- не менять схему базы и публичный контракт панели.

### Критерии готовности

- список разрешений открывается без SQL syntax error;
- карточка разрешения открывается без SQL syntax error;
- полный CI проходит.

### Риски и ограничения

Миграция не требуется, меняется только текст SELECT-запросов.

## После завершения

### Фактически сделано

- alias `grant` заменён на `creation_grant` в обоих запросах;
- добавлен PostgreSQL integration test для `list_creation_grants` и `get_creation_grant`;
- перегенерирован repository layout inventory после добавления тестового модуля.

### Миграции и совместимость

Миграции отсутствуют. Формат данных и Telegram callbacks не менялись.

### Проверки

Запущен финальный GitHub Actions CI с PostgreSQL integration tests, type-check и Docker build.

### PR и commit

PR `#295`; финальный commit будет зафиксирован после merge.

### Незавершённое

После merge требуется повторно открыть панель `🏛 Пространства` и отметить инцидент #63 прочитанным.

### Следующий шаг

Слить hotfix после зелёного CI и выполнить Supervisor Update.
