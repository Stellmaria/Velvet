# Сессия: Фаза 18AF — Alias management и Database.acquire

- Дата: 2026-07-18
- ID: `2026-07-18-phase18af-alias-management`
- Линия/фаза: основное развитие Velvet Archive, Фаза 18AF
- Статус: завершено
- Ветка: `agent/phase18af-alias-management`
- Базовый commit: `09eb91046cd1c7daa9e6a7dd468ddbd181e884ed`

## Перед началом

### Цель

Перевести два connection point в `velvet_bot/alias_management.py` на публичный `Database.acquire()` без изменения alias lookup, удаления и summary-контрактов.

### Исходный контекст

- baseline до работы: 60 внешних обращений в 15 production-файлах;
- `get_character_alias_by_id()` загружает alias и преобразует строку БД в `CharacterAlias`;
- `get_character_alias_summary()` сначала проверяет существование персонажа, затем загружает его алиасы;
- удаление name alias запрещено и делегируется штатному `delete_character_alias()`.

### Планируемый объём

1. Перевести оба connection point на `Database.acquire()`.
2. Сохранить row mapping, missing-item result и summary short-circuit.
3. Добавить source/runtime regression-тесты.
4. Уменьшить baseline до 58 обращений в 14 файлах.
5. Обновить inventory и проектные документы.

### Критерии готовности

- `alias_management.py` не содержит `._require_pool()`;
- модуль содержит ровно два вызова `database.acquire()`;
- alias row mapping и `None` result сохранены;
- summary не вызывает list query для отсутствующего персонажа;
- baseline равен 58/14;
- полный PR CI зелёный.

### Риски и ограничения

- `character_aliases.py` остаётся отдельным следующим срезом;
- SQL и миграции не изменяются;
- Telegram handlers и presentation не затрагиваются.

## После завершения

### Фактически сделано

- оба connection point `alias_management.py` переведены на `Database.acquire()`;
- сохранены alias lookup mapping, missing alias result и character summary short-circuit;
- delete delegation и защита name aliases не изменялись;
- добавлены source/runtime regression-тесты для row mapping, missing alias, summary list и missing character;
- baseline уменьшен с 60/15 до 58/14;
- inventory, project memory, development status и changelog синхронизированы.

### Миграции и совместимость

- миграции и SQL не изменялись;
- публичные сигнатуры и `CharacterAlias` mapping сохранены;
- `character_aliases.py` и его транзакционные сценарии не менялись.

### Проверки

- source regression запрещает `._require_pool()` и требует два `database.acquire()`;
- runtime regression проверяет SQL-маркеры, аргументы, row mapping и short-circuit;
- AST baseline подтверждает 58 внешних обращений в 14 production-файлах;
- GitHub Actions `tests` run 669: success;
- GitHub Actions `docker build` run 254: success;
- GitHub Actions `project notes contract` run 126: success.

### PR и commit

- PR: #135 `Фаза 18AF: Alias management и Database.acquire`;
- production commit: `19a7567fc1c77d34f7a5c979f7ff98a402a7d894`;
- проверенный connector head до финального закрытия worklog: `8d7b5fdfe24956e456adf04925cae873640969a8`.

### Незавершённое

Внутри среза незавершённых задач нет. После merge продолжить Фазой 18AG.

### Следующий шаг

Фаза 18AG: character aliases, 5 connection points. Ожидаемый baseline: 53 обращения в 13 production-файлах.
