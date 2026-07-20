# Сессия: P3D Supervisor handler alias retirement

- Дата: 2026-07-20
- ID: `2026-07-20-p3d-supervisor-alias-retirement`
- Линия/фаза: P3D compatibility alias retirement
- Статус: `завершено`
- Ветка: `agent/p3d-supervisor-alias-retirement`
- Базовый commit: `71bb8655ef0895efb39dd7331f415b783f0d441f`

## Перед началом

### Цель

Удалить восемь завершивших миграцию Supervisor compatibility aliases после перевода оставшихся regression, boundary и architecture tests на canonical presentation modules и отдельный callback contract.

### Исходный контекст

После P3D-Backup в `velvet_bot.handlers` оставалось 17 module aliases. Восемь из них относились к Supervisor: control, status, process, git, logs, console, self и codex. Рабочая Router composition уже использовала `velvet_bot.presentation.telegram.routers.supervisor.*`, а исторические файлы только подменяли модули через `sys.modules`. Остаточные consumers находились в тестах и архитектурных проверках.

### Планируемый объём

- перевести Supervisor status, console, logs, menu и HTTP tests на canonical modules;
- использовать `velvet_bot.presentation.telegram.supervisor.contract` как источник `SupervisorCallback`;
- обновить P3C и access architecture contracts для проверки отсутствия legacy aliases;
- удалить восемь `velvet_bot/handlers/supervisor_*.py` файлов;
- обновить architecture и handler-consumer inventories;
- сохранить команды, callback prefix, Router order, Supervisor HTTP API и runtime operations без изменений;
- не затрагивать analytics channel и ошибку `Message.views`.

### Критерии готовности

- восемь Supervisor alias-файлов отсутствуют;
- canonical Supervisor controllers остаются владельцами Router implementations;
- callback contract имеет единственное определение prefix `sup`;
- handler aliases уменьшаются с 17 до 9;
- consumer-файлы уменьшаются с 15 до 9, references с 40 до 25;
- production legacy imports и missing alias references остаются равны нулю;
- полный CI проходит.

### Риски и ограничения

Supervisor управляет процессами, Git update, логами, self-restart и Codex operations. Срез не меняет runtime-логику, но ошибочный import migration мог бы сломать owner callbacks или test patch targets. Поэтому каждый consumer переведён на конкретный canonical owner до удаления alias. Миграции PostgreSQL не требуются.

## После завершения

### Фактически сделано

- status callback tests импортируют canonical `supervisor.status`;
- console watcher tests импортируют canonical `supervisor.console`;
- logs callback tests импортируют canonical `supervisor.logs` и используют canonical patch target;
- management-menu tests импортируют composition boundary `supervisor.control`;
- общий Supervisor callback test импортирует контракт из `presentation.telegram.supervisor.contract`;
- P3C и phase 10 architecture tests проверяют отсутствие восьми legacy alias-файлов и владение командами canonical controllers;
- удалены `supervisor_control`, `supervisor_status`, `supervisor_process`, `supervisor_git`, `supervisor_logs`, `supervisor_console`, `supervisor_self`, `supervisor_codex`;
- architecture inventory обновлён с 17 до 9 aliases;
- handler consumer inventory обновлён с 15 до 9 consumer-файлов и с 40 до 25 references;
- production Router composition и runtime Supervisor implementation не менялись.

### Миграции и совместимость

Миграции базы данных не требуются. Команды `/supervisor`, `/status`, `/logs`, `/restart`, `/update`, `/rollback`, `/codex`, `/codex_status`, callback prefix `sup`, Supervisor HTTP API и update/restart operations остаются прежними. Исторические Python imports `velvet_bot.handlers.supervisor_*` больше не поддерживаются.

### Проверки

Обновлены status, console, logs, menu, Supervisor core, P3C, phase 10 и machine inventory tests. Полный GitHub CI запускается в PR.

### PR и commit

PR создаётся из ветки `agent/p3d-supervisor-alias-retirement`; итоговый merge commit фиксируется после зелёного CI.

### Незавершённое

В `velvet_bot.handlers` остаются девять analytics aliases, включая отложенный `channel_analytics`. Активных runtime compatibility components остаётся восемь.

### Следующий шаг

Выполнить P3D-Analytics без channel: перевести analytics dashboard и management tests на canonical modules и удалить восемь aliases, оставив `channel_analytics` последним до отдельного исправления ingest-контракта `Message.views`.
