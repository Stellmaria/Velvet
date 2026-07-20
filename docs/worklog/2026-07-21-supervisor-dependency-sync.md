# Сессия: синхронизация зависимостей Supervisor

- Дата: 2026-07-21
- ID: `2026-07-21-supervisor-dependency-sync`
- Линия/фаза: `production hotfix / remote update`
- Статус: `завершено`
- Ветка: `agent/fix-supervisor-dependency-sync`
- Базовый commit: `225af73acf6afe93583ab510d387eaf7acf448d4`

## Перед началом

### Цель

Исправить удалённый self-update Supervisor, который подтягивал новый код и запускал тесты в старом виртуальном окружении без новых пакетов из `requirements.txt`.

### Исходный контекст

После merge Telegram Storage Center удалённый update завершился `ModuleNotFoundError: No module named 'cryptography'`. Новый пакет был указан в `requirements.txt`, но Supervisor не синхронизировал зависимости перед тестами и перезапуском.

### Планируемый объём

- добавить безопасную установку зависимостей через тот же Python, которым запущен Supervisor;
- устанавливать requirements удалённой ветки до передачи self-update bootstrap-задаче;
- повторять проверку текущих requirements при старте Supervisor;
- убрать обязательный import `cryptography` при композиции Telegram router;
- добавить regression tests.

### Критерии готовности

- Router и тестовая коллекция импортируются без установленного `cryptography`;
- remote update заранее устанавливает зависимости целевого commit;
- успешная синхронизация кэшируется по SHA256 requirements и пути Python;
- ошибка pip не помечается как успешная;
- AES-GCM тест продолжает выполняться в CI, где зависимости установлены.

### Риски и ограничения

Первый повторный update после инцидента всё ещё запускается старым bootstrap-кодом. Поэтому encryption import сделан ленивым, а новый Supervisor синхронизирует текущий `requirements.txt` сразу после запуска. Это позволяет выполнить переход без ручного вмешательства в код.

## После завершения

### Фактически сделано

- добавлен `velvet_supervisor.dependencies`;
- remote requirements читаются через `git show origin/main:requirements.txt` и устанавливаются до self-update;
- обычный bot update также предварительно синхронизирует remote requirements;
- при старте Supervisor текущие requirements устанавливаются и кэшируются;
- `cryptography` загружается только при реальном шифровании/расшифровке backup;
- локальная bootstrap-проверка пропускает только AES round-trip, когда пакет ещё не установлен;
- добавлены тесты cache, remote fetch и failed pip.

### Миграции и совместимость

SQL-миграций нет. Формат зашифрованных backup и Telegram Storage index не изменён. Совместимость Windows Task Scheduler сохранена.

### Проверки

- unit tests GitHub Actions;
- Docker build;
- backup restore drill;
- project notes contract.

### PR и commit

PR будет создан после прохождения CI. Итоговый merge commit фиксируется в PR.

### Незавершённое

После merge требуется повторно нажать `Supervisor → Update`. Первый успешный запуск нового Supervisor установит `cryptography==49.0.0`, затем бот запустит Telegram Storage migration.

### Следующий шаг

Проверить живой update на Windows и убедиться, что в operation result присутствует `dependency_sync`, а первый storage migration начал перенос файлов.
