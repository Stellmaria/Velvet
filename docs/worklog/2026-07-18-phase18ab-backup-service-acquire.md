# Сессия: Фаза 18AB — Backup service и Database.acquire

- Дата: 2026-07-18
- ID: `2026-07-18-phase18ab-backup-service-acquire`
- Линия/фаза: основное развитие Velvet Archive, Фаза 18AB
- Статус: частично
- Ветка: `agent/phase18ab-backup-service-acquire`
- Базовый commit: `9ce6320d2bb70dae4c08be7ff94244ed9549a1e0`

## Перед началом

### Цель

Перевести все 15 connection point базового `BackupService` в `velvet_bot/backup_service.py` с приватного `Database._require_pool()` на публичный `Database.acquire()` единым инфраструктурным срезом без изменения backup lifecycle.

### Исходный контекст

- baseline до работы: 82 внешних обращения в 20 production-файлах;
- целевой модуль: `velvet_bot/backup_service.py`, 15 connection points;
- контур охватывает running/completed/failed runs, create/verify/history, settings, retention и scheduled checks.

### Планируемый объём

1. Перевести все 15 connection point на `Database.acquire()`.
2. Сохранить `_run_lock`, status transitions, JSON validation, row mapping, limit/retention clamps и timezone/date semantics.
3. Добавить source/runtime regression-тесты ключевых веток lifecycle.
4. Уменьшить baseline до 67 обращений в 19 файлах и закрыть backup infrastructure category.
5. Обновить inventory, project memory, development status и changelog.

### Критерии готовности

- `BackupService` не содержит внешних `._require_pool()`;
- ровно 15 методов/блоков используют `database.acquire()`;
- backup SQL, dump/restore процессы и manifest не изменены;
- baseline равен 67/19;
- полный PR CI зелёный.

### Риски и ограничения

- нельзя изменить порядок running → valid/invalid/failed;
- cleanup должен сохранять удаление файла, manifest и запись rotation metadata;
- timezone validation и retention clamp 3..100 сохраняются;
- миграции, `pg_dump`, `pg_restore` и Heavy Runtime ТЗ не меняются.

## После завершения

### Фактически сделано

Ожидается реализация.

### Миграции и совместимость

Ожидается реализация.

### Проверки

Ожидается реализация и CI.

### PR и commit

Ожидается открытие PR.

### Незавершённое

Реализация и проверки.

### Следующий шаг

Фаза 18AC: Telegram import persistence, 4 connection points, с сохранением import transaction и dedup semantics.
