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
- baseline: 70 широких исключений в 43 файлах и машинный callback-рейтинг;
- локальные acknowledgment helpers и delegated wrappers отделены от реальных рисков;
- admin/public multi-story callbacks отвечают после universe guard и до picker render;
- status и project memory больше не указывают на завершённую 18AN;
- добавлен AST/source regression-контракт.

### Миграции и совместимость

Миграции, callback payload, permission checks и `SkipHandler` semantics не изменялись.

### Проверки

Требуются полный unit-test workflow, Docker build и project notes contract на финальном head.

### PR и commit

PR #145. Финальный merge выполняется после зелёного CI.

### Незавершённое

Оставшиеся risky callbacks и broad exceptions ведутся в `docs/p2_stability_inventory.*`.

### Следующий шаг

`velvet_bot/handlers/quality_ai.py` · `handle_quality_ai_retry`: перенести acknowledgment до retry/reload операций.
