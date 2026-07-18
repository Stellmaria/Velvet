# Сессия: P2E — AI worker boundaries

- Дата: 2026-07-18
- ID: `2026-07-18-p2e-ai-worker-boundaries`
- Линия/фаза: основное развитие Velvet Archive, P2E
- Статус: завершено
- Ветка: `agent/p2e-ai-worker-boundaries`
- Базовый commit: `de9e55844634cdbc59addb252b317a98d365248a`

## Перед началом

### Цель

Классифицировать три claimed-target AI worker catch как compensation boundaries и закрепить error/cancellation semantics тестами.

### Исходный контекст

P2D оставила baseline 70 raw, 3 approved и 67 unresolved broad exceptions.

### Планируемый объём

1. Классифицировать AI quality worker.
2. Классифицировать semantic vision worker.
3. Классифицировать calibrated quality worker.
4. Проверить `mark_error` и cancellation propagation.
5. Синхронизировать inventory и документы.

### Критерии готовности

- неизвестная ошибка claimed target вызывает `mark_error`;
- cancellation не преобразуется в item error;
- provider-specific branch не меняется;
- unresolved baseline уменьшается 67 → 64;
- полный PR CI зелёный.

### Риски и ограничения

Raw catches сохраняются, потому что target уже claimed и обязан получить terminal/retry state. Классификация не считается удалением catch.

## После завершения

### Фактически сделано

- три AI worker boundaries отмечены approved markers;
- добавлены общие behavior tests;
- approved baseline увеличен 3 → 6;
- unresolved baseline уменьшен 67 → 64;
- inventory и проектные документы синхронизированы.

### Миграции и совместимость

Миграции, provider API, retry policy и permanent-error semantics не изменялись.

### Проверки

Финальный head после выравнивания marker convention проходит unit tests, Docker build и project notes contract.

### PR и commit

PR #152. Финальный merge выполняется после зелёного CI.

### Незавершённое

Остаётся 64 unresolved broad exceptions.

### Следующий шаг

Broad-exception triage в `velvet_bot/ai_job_runtime.py`.
