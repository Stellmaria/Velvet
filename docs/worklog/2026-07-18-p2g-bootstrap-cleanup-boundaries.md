# Сессия: P2G — bootstrap cleanup boundaries

- Дата: 2026-07-18
- ID: `2026-07-18-p2g-bootstrap-cleanup-boundaries`
- Линия/фаза: Velvet Archive, P2G
- Статус: завершено
- Ветка: `agent/p2g-bootstrap-cleanup-boundaries`
- Базовый commit: `fba5cc2791d371bac24780aab0f8566f48758ef9`

## Перед началом

### Цель
Проверить изоляцию независимых shutdown-шагов.

### Исходный контекст
Baseline: 63 unresolved broad exceptions.

### Планируемый объём
Пять markers, behavior tests, inventory и документы.

### Критерии готовности
Обычная ошибка не останавливает последующие cleanup-шаги, cancellation не подавляется, CI зелёный.

### Риски и ограничения
Fatal-reporting catches `run_application()` не входят в этот срез.

## После завершения

### Фактически сделано
Пять cleanup boundaries классифицированы, baseline 63 → 58.

### Миграции и совместимость
Миграции и lifecycle API не менялись.

### Проверки
Финальный head проходит unit tests, Docker build и project notes contract.

### PR и commit
PR #155. Merge после зелёного CI.

### Незавершённое
58 unresolved broad exceptions.

### Следующий шаг
Fatal-reporting boundaries в `velvet_bot/app/bootstrap.py`.
