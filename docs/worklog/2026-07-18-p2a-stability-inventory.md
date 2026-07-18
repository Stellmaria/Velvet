# Сессия: P2A — stability inventory

- Дата: 2026-07-18
- ID: `2026-07-18-p2a-stability-inventory`
- Линия/фаза: основное развитие Velvet Archive, P2A
- Статус: завершено
- Ветка: `agent/p2-stability-inventory`
- Базовый commit: `34480b8dea26ecd98c01c814442de8abe7593677`

## Перед началом

### Цель

Создать измеримый baseline callback acknowledgment и широких `except Exception`, удалить устаревшие ссылки на Фазу 18AN и исправить первый подтверждённый callback-риск.

### Исходный контекст

Фаза 18 закрыта baseline 0/0. P2-долг не имел машинного inventory. В status и project memory оставались старые пункты 18AN.

### Планируемый объём

1. Просканировать production AST.
2. Разделить early, guarded, delegated, late и missing acknowledgment.
3. Зафиксировать широкие исключения.
4. Добавить CI-контракт inventory.
5. Исправить первый подтверждённый долгий callback-сценарий.

### Критерии готовности

- inventory синхронизирован с AST;
- устаревшие ссылки на 18AN удалены;
- multi-story handlers отвечают до тяжёлого рендера;
- `SkipHandler` guard сохранён;
- полный PR CI зелёный.

### Риски и ограничения

Один lookup до acknowledgment классифицируется как guarded, поскольку он может определять владение callback через `SkipHandler`. AST-эвристика не заменяет чтение конкретного handler.

## После завершения

### Фактически сделано

- создан JSON/Markdown inventory;
- зафиксировано 70 широких `except Exception` в 43 production-файлах;
- из 97 callback handlers осталось 5 реально late/missing callbacks в 3 файлах;
- 20 callbacks классифицированы как guarded после одного lookup, 4 как delegated wrappers;
- локальные acknowledgment helpers отделены от реальных рисков;
- admin/public multi-story callbacks отвечают после universe guard и до picker render;
- status и project memory больше не указывают на завершённую 18AN;
- добавлен AST/source regression-контракт.

### Миграции и совместимость

Миграции, callback payload, permission checks и `SkipHandler` semantics не изменялись.

### Проверки

Финальный head должен пройти полный unit-test workflow, Docker build и project notes contract.

### PR и commit

PR #147. Финальный merge выполняется после зелёного CI.

### Незавершённое

Оставшиеся 5 risky callbacks и 70 broad exceptions ведутся в `docs/p2_stability_inventory.*`.

### Следующий шаг

`velvet_bot/handlers/quality_ai.py` · `handle_quality_ai_retry`: перенести acknowledgment до retry/reload операций.
