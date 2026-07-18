# Сессия: Фаза 18AL — Media sets и Database.acquire

- Дата: 2026-07-18
- ID: `2026-07-18-phase18al-media-sets`
- Линия/фаза: основное развитие Velvet Archive, Фаза 18AL
- Статус: частично
- Ветка: `agent/phase18al-media-sets`
- Базовый commit: `16559e825eeb4de2901895f75393225518ce7a54`

## Перед началом

### Цель

Перевести девять connection point в `velvet_bot/media_sets.py` на публичный `Database.acquire()` без изменения discovery, candidate review, set creation и duplicate workflows.

### Исходный контекст

- baseline до работы: 23 внешних обращения в 9 production-файлах;
- discovery читает media contexts одним соединением и сохраняет drafts второй транзакцией;
- candidate list делегирует detail loading и нормализует страницу;
- toggle и decision возвращают nullable boolean/boolean mappings;
- create set блокирует candidate и media rows, требует минимум два выбранных материала и распространяет prompt URL;
- duplicate conversion создаёт pending set candidate из похожей пары в одной транзакции;
- duplicate deletion блокирует пару и файл, сохраняет archive references и каскадно чистит связанные таблицы.

### Планируемый объём

1. Перевести девять connection point на `Database.acquire()`.
2. Сохранить двухэтапный discovery и transaction boundaries.
3. Сохранить candidate pagination, detail и item mapping.
4. Сохранить toggle/decision validation и result mappings.
5. Сохранить create-set locks, minimum selection и prompt propagation.
6. Сохранить duplicate conversion и score floor.
7. Сохранить duplicate deletion archive references и cascade order.
8. Добавить source/runtime regression-тесты.
9. Уменьшить baseline до 14 обращений в 8 файлах.
10. Закрыть legacy query wave и обновить проектные документы.

### Критерии готовности

- `media_sets.py` не содержит `._require_pool()`;
- модуль содержит ровно девять вызовов `database.acquire()`;
- compare с базой показывает только девять замен границы;
- discovery использует два connection context и одну write transaction;
- candidate page/detail/toggle/decision contracts проверены;
- create set, duplicate conversion и duplicate deletion transactions проверены;
- cascade deletion order и archive-reference mapping сохранены;
- baseline равен 14/8;
- legacy query category отсутствует в baseline;
- полный PR CI зелёный.

### Риски и ограничения

- SQL и миграции не изменяются;
- grouping heuristics, filename family и visual scoring не меняются;
- публичные dataclasses и пользовательские ошибки сохраняются;
- application/presentation modules остаются следующей отдельной волной.

## После завершения

### Фактически сделано

- все девять connection point `media_sets.py` переведены на `Database.acquire()`;
- compare с базовым commit подтвердил ровно 9 additions и 9 deletions в production-файле из 884 строк;
- сохранены context loading, draft generation и отдельная write transaction;
- сохранены candidate upsert, candidate-item upsert и inserted-count semantics;
- сохранены candidate pagination/detail, item characters и selected-count mapping;
- сохранены toggle nullable result и decision validation/status mapping;
- сохранены create-set locks, minimum two items, media assignment, prompt propagation и accepted status;
- сохранены duplicate conversion locks, sorted media ids, score floor и ignored duplicate status;
- сохранены duplicate deletion guards, archive references и каскадная очистка восьми связанных операций;
- добавлены source/runtime regression-тесты для всех девяти persistence entry points;
- baseline уменьшен с 23/9 до 14/8;
- legacy query-модули полностью удалены из baseline;
- inventory, project memory, development status и changelog синхронизированы.

### Миграции и совместимость

- миграции и SQL не изменялись;
- публичные Python-сигнатуры и dataclasses не изменялись;
- grouping heuristics, visual scoring и тексты ошибок сохранены.

### Проверки

- source regression запрещает `._require_pool()` и требует девять `database.acquire()`;
- runtime regression проверяет discovery, page/detail, toggle/decision, create set, duplicate conversion и deletion cascade;
- AST baseline ожидает 14 внешних обращений в 8 production-файлах;
- требуется полный PR CI.

### PR и commit

- PR будет создан после синхронизации документации;
- production commit: `687b3b64cfad3e570087c5f0632a3e280008a6b4`;
- test commit: `0e287f5e14ead6c0fe88dd179088ba6220f18f99`.

### Незавершённое

Требуется полный зелёный PR CI и финальное закрытие записи перед merge.

### Следующий шаг

Фаза 18AM: вынести два persistence connection point из `media_set_ai_discovery.py` в repository boundary. Ожидаемый baseline: 12 обращений в 7 production-файлах.
