# Сессия: P2H — bootstrap fatal boundaries

- Дата: 2026-07-18
- ID: `2026-07-18-p2h-bootstrap-fatal-boundaries`
- Линия/фаза: Velvet Archive, P2H
- Статус: завершено
- Ветка: `agent/p2h-bootstrap-fatal-boundaries`
- Базовый commit: `0c89804bfe1e7c65ff4878eb36396d669fbadaf7`

## Перед началом

### Цель
Разделить lifecycle catch и fallback отчёта критической ошибки.

### Исходный контекст
Baseline: 58 unresolved broad exceptions.

### Планируемый объём
Helper, два markers, behavior tests и AST regeneration.

### Критерии готовности
Ошибка отчёта не заменяет исходную, cancellation не подавляется, CI зелёный.

### Риски и ограничения
Startup dependencies и cleanup порядок не меняются.

## После завершения

### Фактически сделано
Fatal reporting вынесен в helper, baseline 58 → 56.

### Миграции и совместимость
Миграции и dispatcher lifecycle не менялись.

### Проверки
Unit tests, Docker build и project notes contract.

### PR и commit
PR создаётся после runner.

### Незавершённое
56 unresolved broad exceptions.

### Следующий шаг
`velvet_bot/audit.py`.
