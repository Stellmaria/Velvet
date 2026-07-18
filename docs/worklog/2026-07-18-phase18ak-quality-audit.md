# Сессия: Фаза 18AK — Quality audit и Database.acquire

- Дата: 2026-07-18
- ID: `2026-07-18-phase18ak-quality-audit`
- Линия/фаза: основное развитие Velvet Archive, Фаза 18AK
- Статус: частично
- Ветка: `agent/phase18ak-quality-audit`
- Базовый commit: `398f1d24399b2f7ddb155d471c8f4247c444fb4d`

## Перед началом

### Цель

Перевести пять connection point в `velvet_bot/quality_audit.py` на публичный `Database.acquire()` без изменения summary counters, пагинации quality issues и reset broken checks.

### Исходный контекст

- baseline до работы: 28 внешних обращений в 10 production-файлах;
- quality summary объединяет тринадцать счётчиков, включая story-required universes;
- character issue pages используют разные SQL conditions и динамические placeholder-позиции;
- media issue pages вычисляют newest-first media offset для перехода к материалу;
- unresolved hashtags получают стабильную нумерацию внутри страницы;
- reset broken checks возвращает количество изменённых строк из PostgreSQL command status.

### Планируемый объём

1. Перевести пять connection point на `Database.acquire()`.
2. Сохранить summary SQL и `QualitySummary` mapping.
3. Сохранить dynamic character filters и placeholder positions.
4. Сохранить media conditions, error priority и media offset mapping.
5. Сохранить unresolved numbering и page clamps.
6. Сохранить reset affected-row mapping.
7. Добавить source/runtime regression-тесты.
8. Уменьшить baseline до 23 обращений в 9 файлах.
9. Обновить inventory и проектные документы.

### Критерии готовности

- `quality_audit.py` не содержит `._require_pool()`;
- модуль содержит ровно пять вызовов `database.acquire()`;
- compare с базой показывает только пять замен границы;
- summary counters и `total_problems` проверены;
- `missing_story` использует правильные `$1/$2/$3` positions;
- media offset и detail priority проверены;
- unresolved ids учитывают page offset;
- reset возвращает affected row count;
- baseline равен 23/9;
- полный PR CI зелёный.

### Риски и ограничения

- SQL и миграции не изменяются;
- sections и пользовательские ошибки не меняются;
- публичные dataclasses и page semantics сохраняются;
- handlers и presentation не затрагиваются;
- media sets остаётся следующим отдельным срезом.

## После завершения

### Фактически сделано

- все пять connection point `quality_audit.py` переведены на `Database.acquire()`;
- compare с базовым commit подтвердил ровно 5 additions и 5 deletions в production-файле;
- сохранены все summary counters, required-universe argument и `total_problems` semantics;
- сохранены character conditions, dynamic placeholders и page clamps;
- сохранены media conditions, newest-first offset и detail priority;
- сохранены unresolved hashtag numbering и row mapping;
- сохранён reset broken checks и affected-row parsing;
- invalid sections по-прежнему отклоняются до DB access;
- добавлены source/runtime regression-тесты для всех пяти persistence entry points;
- baseline уменьшен с 28/10 до 23/9;
- inventory, project memory, development status и changelog синхронизированы.

### Миграции и совместимость

- миграции и SQL не изменялись;
- публичные Python-сигнатуры и dataclasses не изменялись;
- section names, тексты ошибок и pagination semantics сохранены.

### Проверки

- source regression запрещает `._require_pool()` и требует пять `database.acquire()`;
- runtime regression проверяет summary, character/media/unresolved pages и reset;
- AST baseline ожидает 23 внешних обращения в 9 production-файлах;
- требуется полный PR CI.

### PR и commit

- PR будет создан после синхронизации документации;
- production commit: `bbe424556aa8ecff172e75a687a363d065f1a6d4`;
- test commit: `e382ad98b792f375a1ef7b14298e8146dd87ecd5`.

### Незавершённое

Требуется полный зелёный PR CI и финальное закрытие записи перед merge.

### Следующий шаг

Фаза 18AL: media sets, 9 connection points. Ожидаемый baseline: 14 обращений в 8 production-файлах.
