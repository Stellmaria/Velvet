# Сессия: P3D Backup handler alias retirement

- Дата: 2026-07-20
- ID: `2026-07-20-p3d-backup-alias-retirement`
- Линия/фаза: P3D compatibility alias retirement
- Статус: `завершено`
- Ветка: `agent/p3d-backup-alias-retirement-v2`
- Базовый commit: `f2eefcde2185178fb18599f4c0edbe6b20b27123`

## Перед началом

### Цель

Удалить завершивший миграцию compatibility alias `velvet_bot.handlers.backup_center` после перевода оставшихся backup regression-тестов на canonical presentation controller.

### Исходный контекст

После P3D-Core в `velvet_bot.handlers` оставалось 18 module aliases. Backup-контроллер уже физически находился в `velvet_bot.presentation.telegram.routers.quality_operations_controllers.backup_center`, но два теста продолжали импортировать исторический путь. Alias не содержал собственной логики и только подменял модуль через `sys.modules`.

### Планируемый объём

- перевести backup boundary и callback-limit tests на canonical module;
- расширить P3C quality contract, чтобы `backup_center` считался удалённым alias;
- удалить `velvet_bot/handlers/backup_center.py`;
- обновить architecture и handler-consumer inventories;
- сохранить runtime Router composition и backup contracts без изменений;
- не смешивать с P3D-Supervisor.

### Критерии готовности

- старый backup alias-файл отсутствует;
- canonical backup controller остаётся владельцем Router и callback implementation;
- backup boundary tests проходят через canonical import;
- handler aliases уменьшаются с 18 до 17;
- missing alias references остаются равны нулю;
- полный CI проходит.

### Риски и ограничения

Срез не меняет создание, ротацию, валидацию или восстановление backup. Ошибка в import migration могла бы сломать только тестовый или внешний legacy consumer, поэтому удаление выполняется после нулевого repository inventory. Миграции PostgreSQL не требуются.

## После завершения

### Фактически сделано

- `tests/test_p2p_backup_center_boundary.py` переведён на canonical backup controller;
- `tests/test_phase5_discussion_and_backups.py` импортирует `BackupCallback` из canonical presentation module;
- P3C quality contract помечает `backup_center` как retired alias и проверяет отсутствие файла;
- `velvet_bot/handlers/backup_center.py` удалён;
- architecture inventory обновлён с 18 до 17 aliases;
- handler consumer inventory обновлён с 16 до 15 consumer-файлов и с 42 до 40 references;
- production Router composition, backup service и runtime worker не менялись.

### Миграции и совместимость

Миграции базы данных не требуются. Команды `/backup`, callback prefix, BackupService, retention policy, startup backup и restore-контракты остаются прежними. Исторический Python import `velvet_bot.handlers.backup_center` больше не поддерживается.

### Проверки

Обновлены backup boundary, phase 5, P3C quality и machine inventory tests. Полный GitHub CI запускается в PR.

### PR и commit

PR создаётся из ветки `agent/p3d-backup-alias-retirement-v2`; итоговый merge commit фиксируется после зелёного CI.

### Незавершённое

В `velvet_bot.handlers` остаются восемь Supervisor aliases и девять analytics aliases, включая отложенный `channel_analytics`.

### Следующий шаг

Выполнить P3D-Supervisor отдельным срезом: перевести Supervisor tests на canonical presentation modules, удалить восемь aliases и проверить status, logs, process, git update, self-restart и Codex operations.
