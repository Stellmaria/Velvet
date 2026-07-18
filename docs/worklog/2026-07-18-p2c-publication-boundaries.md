# Сессия: P2C — publication broad boundaries

- Дата: 2026-07-18
- ID: `2026-07-18-p2c-publication-boundaries`
- Линия/фаза: основное развитие Velvet Archive, P2C
- Статус: завершено
- Ветка: `agent/p2c-publication-boundaries`
- Базовый commit: `f19ad75b304d94d5b971e7869a34bcd1ecbdf5e2`

## Перед началом

### Цель

Классифицировать два broad exceptions publication service как явные orchestration boundaries и закрепить их компенсационные контракты тестами.

### Исходный контекст

P2B закрыла callback late/missing baseline. Broad inventory содержала 70 необработанных записей в 43 файлах, включая два `except Exception` publication service.

### Планируемый объём

1. Отметить claim compensation boundary в `publish()`.
2. Отметить per-item isolation boundary в `process_due_once()`.
3. Разделить raw, approved и unresolved broad counts.
4. Добавить tests compensation, isolation и cancellation.
5. Синхронизировать inventory и проектные документы.

### Критерии готовности

- raw broad count остаётся честным;
- approved boundaries имеют inline marker и tests;
- unresolved broad baseline уменьшается 70 → 68;
- cancellation не подавляется;
- полный PR CI зелёный.

### Риски и ограничения

Broad catch внутри claim lifecycle сохраняется намеренно: неизвестная ошибка после claim должна перевести draft в error. Scheduled loop сохраняет изоляцию отдельных draft. Классификация не считается удалением raw catch.

## После завершения

### Фактически сделано

- два publication catches отмечены approved boundary markers;
- inventory schema разделяет raw, approved и unresolved debt;
- raw baseline остаётся 70/43;
- approved baseline равен 2;
- unresolved baseline уменьшен до 68;
- добавлены tests delivery failure compensation, mark-published compensation, scheduled isolation и cancellation propagation.

### Миграции и совместимость

Миграции, API service, repository и delivery protocols не изменялись.

### Проверки

Требуются unit tests, Docker build и project notes contract на финальном head.

### PR и commit

PR создаётся после runner; номер фиксируется финальным connector-коммитом.

### Незавершённое

Остаётся 68 unresolved broad exceptions.

### Следующий шаг

Broad-exception triage в `velvet_bot/domains/media_quality/service.py`.
