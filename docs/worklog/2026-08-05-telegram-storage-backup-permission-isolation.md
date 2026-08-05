# Сессия: Telegram Storage backup permission isolation

- Дата: 2026-08-05
- ID: `2026-08-05-error-449-telegram-storage`
- Линия/фаза: hotfix / эксплуатационная стабилизация Telegram Storage
- Статус: `частично`
- Ветка: `fix/telegram-storage-backup-permission-isolation`
- Базовый commit: `1a56d7b9d2fea7a967ba12c5a119b53d0dfb8e5c`

## Перед началом

### Цель

Не допустить, чтобы один backup-файл с недостаточными Unix-правами завершал весь проход Telegram Storage Migration и блокировал обработку остальных резервных копий и последующих категорий хранилища.

### Исходный контекст

Ошибка Error Center #449 повторялась при вычислении SHA-256 файла `/app/backups/pre-z032-20260804T183304Z-ca860bdf038c.dump`. `PermissionError` возникал до локального `try` в `_migrate_backups`, поэтому доходил до общего boundary метода `run` и превращал ошибку одного файла в fatal-ошибку всего прохода.

Изменение относится к существующей функции зашифрованной репликации backup в Telegram Storage. Оно повышает надёжность и изоляцию отказов, не добавляет новую предметную область и не меняет backup-формат, encryption contract или deletion policy.

### Планируемый объём

- перенести вычисление source SHA-256 и подготовку manifest внутрь per-item exception boundary;
- сохранить cleanup временных ZIP/encrypted/verify файлов;
- добавить regression-тест с первым нечитаемым и вторым успешно обрабатываемым backup;
- не менять миграции, Telegram API contract и правила удаления локальных файлов.

### Критерии готовности

- `PermissionError` одного backup учитывается как `backups.failed`;
- цикл продолжает обработку следующих backup items;
- успешный следующий backup загружается и помечается offloaded;
- итоговый migration summary имеет статус `partial`, а не fatal failure;
- обязательные CI checks PR проходят.

### Риски и ограничения

Исправление изолирует отказ, но не исправляет права уже существующего файла на production-хосте. Такой файл останется локально и будет повторно отмечаться failed до изменения host permissions или удаления по отдельному подтверждённому эксплуатационному решению. Автоматически ослаблять права или удалять нечитаемый dump код не будет.

## После завершения

### Фактически сделано

В `_migrate_backups` вычисление source digest, проверка manifest и формирование storage manifest перенесены внутрь существующего per-item exception boundary. Ошибка чтения теперь очищает только временные файлы текущего элемента, записывается через `_record_failure` и не прерывает цикл.

Добавлен изолированный async regression-тест: первый backup выбрасывает `PermissionError`, второй проходит упаковку, проверку, загрузку и `mark_backup_offloaded`.

### Изменённые модули и контракты

- `velvet_bot/domains/telegram_storage/service.py`: расширена существующая граница изоляции backup item;
- `tests/test_telegram_storage_backup_permission_isolation.py`: новый regression contract.

Публичные команды, PostgreSQL schema, backup dump format, AES-256-GCM+scrypt:v2 metadata и uploader contract не изменены.

### Миграции и совместимость

Миграции не требуются. Изменение обратно совместимо с tracked и untracked backup items, включая элементы с уже сохранённым `sha256`.

### Проверки

- diff review: production-изменение ограничено перемещением подготовки backup внутрь существующего `try`;
- regression-test добавлен, запуск и полный CI фиксируются после открытия PR.

### PR и commit

Ветка содержит commits:

- `4859a5320bd6c79b803ec006c71ed75b6b8cfe83` — regression-test;
- `70ec32a7e83d7b51800f7d2a3e7970b8053704d9` — production fix.

Номер PR и итоговый merge commit будут записаны после зелёных checks.

### Незавершённое

- обязательные CI checks ещё не подтверждены;
- production-файл с ошибочными правами требует отдельного host-level исправления и повторного storage scan.

### Следующий шаг

Открыть PR, дождаться обязательных checks, обновить эту запись фактическими результатами и слить PR. После deployment исправить права конкретного dump и выполнить повторный Telegram Storage Migration.
