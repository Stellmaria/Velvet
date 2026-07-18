# Сессия: Фаза 18AA — Backup runtime и Database.acquire

- Дата: 2026-07-18
- ID: `2026-07-18-phase18aa-backup-runtime-acquire`
- Линия/фаза: основное развитие Velvet Archive, Фаза 18AA
- Статус: частично
- Ветка: `agent/phase18aa-backup-runtime-acquire`
- Базовый commit: `9b2b5d10067448181db0b21b49d34637a0f49b50`

## Перед началом

### Цель

Перевести два connection point runtime-hardened `BackupService` в `velvet_bot/backup_runtime.py` с приватного `Database._require_pool()` на публичный `Database.acquire()` без изменения schedule, dump creation и retention.

### Исходный контекст

- baseline до работы: 84 внешних обращения в 21 production-файле;
- целевой модуль: `velvet_bot/backup_runtime.py`, 2 connection points;
- методы читают expected tables конкретного backup и проверяют, запускался ли тип backup в локальную дату.

### Планируемый объём

1. Перевести `_expected_tables_for_record()` и `_ran_kind_today()` на `Database.acquire()`.
2. Сохранить JSON decode, timezone/date semantics и backup-kind filters.
3. Добавить source/runtime regression-тесты.
4. Уменьшить baseline до 82/20 и обновить документы.

### Критерии готовности

- runtime backup service не содержит `._require_pool()`;
- оба метода используют публичную границу;
- schedule/dump/cleanup код не изменён;
- baseline равен 82/20;
- полный PR CI зелёный.

### Риски и ограничения

- базовый `backup_service.py` остаётся отдельной Фазой 18AB;
- внешние `pg_dump`/`pg_restore` процессы не изменяются;
- миграции не изменяются;
- Heavy Runtime ТЗ не включается.

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

Фаза 18AB: базовый backup service, 15 connection points, единым инфраструктурным контрактом.
