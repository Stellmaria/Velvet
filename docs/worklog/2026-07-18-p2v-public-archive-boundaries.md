# Сессия: P2V — public archive boundaries

- Дата: 2026-07-18
- ID: `2026-07-18-p2v-public-archive-boundaries`
- Линия/фаза: Velvet Archive, P2V
- Статус: завершено
- Ветка: `agent/p2v-public-archive-boundaries`
- Базовый commit: `55f449b6026b2d9861412655d0747198360bda39`

## Перед началом

### Цель
Разобрать пять broad boundaries публичного архива и убрать ложные сообщения об ошибке после успешного изменения данных.

### Исходный контекст
33 unresolved broad exceptions в 23 production-файлах.

### Планируемый объём
Два preview fallback, like/sub/download reporting boundaries, behavior tests, inventory и документы.

### Критерии готовности
Preview fallback сохраняет документ; DB failure даёт user-facing alert; успешный commit не объявляется неудачным при сбое Telegram UI; cancellation пробрасывается; CI зелёный.

### Риски и ограничения
Фильтры публичного архива, SQL, download allowlist и callback actions не меняются.

## После завершения

### Фактически сделано
Пять boundaries классифицированы. Like/sub/download разделяют изменение данных и Telegram presentation. Baseline 33 → 28.

### Миграции и совместимость
Миграции и публичные callback actions не менялись.

### Проверки
Tests, Docker build и project notes contract.

### PR и commit
PR #172; итоговый merge commit фиксируется после зелёного CI.

### Незавершённое
28 unresolved broad exceptions.

### Следующий шаг
`velvet_bot/handlers/public_manager.py`.
