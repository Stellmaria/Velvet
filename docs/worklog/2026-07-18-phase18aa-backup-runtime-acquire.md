# Сессия: Фаза 18AA — Backup runtime и Database.acquire

- Дата: 2026-07-18
- ID: `2026-07-18-phase18aa-backup-runtime-acquire`
- Линия/фаза: основное развитие Velvet Archive, Фаза 18AA
- Статус: завершено
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

- `_expected_tables_for_record()` и `_ran_kind_today()` переведены на `Database.acquire()`;
- сохранены JSON decode, backup id filter, backup-kind filter и timezone/local-date semantics;
- dump creation, validation, cleanup и missing-pg_dump fallback не изменялись;
- добавлены source/runtime regression-тесты;
- baseline уменьшен с 84/21 до 82/20;
- inventory, project memory, development status и changelog обновлены.

### Миграции и совместимость

- миграции не изменялись;
- `pg_dump`/`pg_restore`, manifest и retention contracts не изменялись;
- публичные Python-контракты не изменялись.

### Проверки

- production commit `1c52e952368585945a0b70204bad9bb9c6afd25c`: diff содержит только две замены private boundary на public boundary;
- PR CI `tests #639`, run `29639684982`: успешно;
- PR CI `docker build #229`, run `29639684961`: успешно;
- PR CI `project notes contract #102`, run `29639684974`: успешно.

### PR и commit

- PR: #129 `Фаза 18AA: Backup runtime и Database.acquire`;
- production commit: `1c52e952368585945a0b70204bad9bb9c6afd25c`;
- проверенный CI head: `0d8800d5bcb84677696c05f31e87956e8989940d`.

### Незавершённое

В рамках Фазы 18AA незавершённых изменений нет. Живая проверка `pg_dump` не требуется, потому что внешние процессы не менялись.

### Следующий шаг

Фаза 18AB: базовый backup service, 15 connection points, единым инфраструктурным контрактом.
