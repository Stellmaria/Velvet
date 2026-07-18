# Сессия: Фаза 18AG — Character aliases и Database.acquire

- Дата: 2026-07-18
- ID: `2026-07-18-phase18ag-character-aliases`
- Линия/фаза: основное развитие Velvet Archive, Фаза 18AG
- Статус: частично
- Ветка: `agent/phase18ag-character-aliases`
- Базовый commit: `6448dd79eeb1b8ad7a9371b7f9a9967f859f5c9d`

## Перед началом

### Цель

Перевести пять connection point в `velvet_bot/character_aliases.py` на публичный `Database.acquire()` без изменения создания, списка, удаления и транзакционной перестройки hashtag-связей.

### Исходный контекст

- baseline до работы: 58 внешних обращений в 14 production-файлах;
- `ensure_name_aliases()` создаёт обязательные name aliases и считает только реальные вставки;
- `list_character_aliases()` сохраняет name-first ordering и отображение строк в `CharacterAlias`;
- `add_character_alias()` нормализует ввод, проверяет конфликт владельца, делает upsert и связывает подходящие hashtags;
- `delete_character_alias()` не удаляет name aliases и отвязывает hashtag только при отсутствии оставшегося alias;
- `rebuild_hashtag_character_links()` выполняет полный reset и повторное связывание в одной транзакции.

### Планируемый объём

1. Перевести пять connection point на `Database.acquire()`.
2. Сохранить validation, conflict handling, upsert и hashtag update contracts.
3. Сохранить delete guard и транзакционный rebuild.
4. Добавить source/runtime regression-тесты.
5. Уменьшить baseline до 53 обращений в 13 файлах.
6. Обновить inventory и проектные документы.

### Критерии готовности

- `character_aliases.py` не содержит `._require_pool()`;
- модуль содержит ровно пять вызовов `database.acquire()`;
- name-alias insert count и ordered list mapping сохранены;
- add/delete hashtag semantics сохранены;
- rebuild использует один transaction context и возвращает `(matched, total)`;
- baseline равен 53/13;
- полный PR CI зелёный.

### Риски и ограничения

- SQL и миграции не изменяются;
- нормализация alias остаётся прежней;
- handlers и presentation не затрагиваются;
- analytics modules остаются следующей отдельной группой срезов.

## После завершения

### Фактически сделано

- все пять connection point `character_aliases.py` переведены на `Database.acquire()`;
- сохранены name-alias seeding, insert count и пропуск пустой нормализации;
- сохранены name-first ordering и `CharacterAlias` row mapping;
- сохранены input cleanup, length validation, conflict check, upsert и hashtag linking;
- сохранены защита name aliases, conditional unlink и empty-alias short-circuit;
- сохранён полный rebuild внутри одной транзакции с matched/total mapping;
- добавлены source/runtime regression-тесты для каждого persistence-сценария;
- baseline уменьшен с 58/14 до 53/13;
- inventory, project memory, development status и changelog синхронизированы.

### Миграции и совместимость

- миграции и SQL не изменялись;
- публичные Python-сигнатуры и `CharacterAlias` dataclass не изменялись;
- normalization rules и тексты ошибок сохранены.

### Проверки

- source regression запрещает `._require_pool()` и требует пять `database.acquire()`;
- runtime regression проверяет seeding, listing, add, delete и transactional rebuild;
- AST baseline ожидает 53 внешних обращения в 13 production-файлах;
- требуется полный PR CI.

### PR и commit

- PR будет создан после синхронизации документации;
- production commit: `0d7ce7b521074dc1d313b0a99b7b089091be83ac`;
- test commit: `5d396880c3e32e2d5216948bdb786b207cb39746`.

### Незавершённое

Требуется полный зелёный PR CI и финальное закрытие записи перед merge.

### Следующий шаг

Фаза 18AH: analytics dashboard, 8 connection points. Ожидаемый baseline: 45 обращений в 12 production-файлах.
