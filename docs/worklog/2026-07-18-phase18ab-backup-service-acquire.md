# Сессия: Фаза 18AB — Backup service и Database.acquire

- Дата: 2026-07-18
- ID: `2026-07-18-phase18ab-backup-service-acquire`
- Линия/фаза: основное развитие Velvet Archive, Фаза 18AB
- Статус: завершено
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

- все 15 connection point базового `BackupService` переведены на `Database.acquire()`;
- сохранены running/completed/failed transitions, create/verify/history, settings, scheduled checks и retention cleanup;
- добавлены regression-тесты публичной DB-границы, running run, validation payload, settings clamp и timezone/date check;
- рассинхронизированный inventory-тест исправлен с 82/20 на фактические 67/19;
- backup infrastructure полностью удалён из private pool baseline;
- обновлены machine baseline, inventory, project memory, development status и changelog.

### Миграции и совместимость

- миграции не изменялись;
- SQL, `pg_dump`, `pg_restore`, manifest и публичные Python-контракты не изменялись;
- порядок backup lifecycle и rotation metadata сохранён;
- Heavy Runtime ТЗ в срез не включалось.

### Проверки

- production commit `b67631c28fa591a0cecd08a9f110052ea007c335`: diff содержит 15 точечных замен private boundary на public boundary;
- первый CI `tests #642` обнаружил только устаревшие ожидаемые числа inventory 82/20;
- inventory test синхронизирован commit `b8f249f6a006dc79eca7effc0e77ba03346962a3`;
- CI head `dcb0bedd20729b3bd8f314fbac288eccb8e3dc17`:
  - `tests #647`, run `29641048460`: успешно;
  - `docker build #237`, run `29641048444`: успешно;
  - `project notes contract #109`, run `29641048437`: успешно.

### PR и commit

- PR: #130 `Фаза 18AB: Backup service и Database.acquire`;
- production commit: `b67631c28fa591a0cecd08a9f110052ea007c335`;
- проверенный CI head до закрытия worklog: `dcb0bedd20729b3bd8f314fbac288eccb8e3dc17`.

### Незавершённое

В рамках Фазы 18AB незавершённых изменений нет. Живая проверка `pg_dump`/`pg_restore` не требуется для этого среза, потому что внешние процессы и их аргументы не менялись.

### Следующий шаг

Фаза 18AC: Telegram import persistence, 4 connection points, с сохранением одной import transaction, SHA-256 dedup и существующего parser/mapping поведения.
