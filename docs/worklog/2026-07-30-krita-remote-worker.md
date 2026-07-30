# 2026-07-30 — удалённый Windows Krita worker

- Дата: 2026-07-30
- ID: krita-remote-worker
- Линия/фаза: Линия C — server migration / Windows worker separation
- Статус: `частично`
- Ветка: `agent/krita-remote-worker`
- Базовый commit: `e73dc9b5c28ef938455123e824f1c60b3760682e`

## Перед началом

### Цель

Отделить Krita от основного Velvet Bot перед переносом на Linux VPS. Сервер должен владеть PostgreSQL-очередью, исходниками и результатами, а Windows-компьютер должен выполнять только локальный Krita Python API без production-секретов и входящих портов.

### Исходный контекст

Watermark domain уже имеет PostgreSQL revisions, локальный файловый bridge, восстановление `*.processing`, безопасные пути, Telegram preview и финальное подтверждение. Этот контур предполагал общий Windows-каталог между ботом и Krita и поэтому блокировал полное отключение локального бота после server migration.

### Планируемый объём

- добавить remote worker lease и heartbeat в PostgreSQL;
- добавить защищённый HTTP API внутри bot process;
- публиковать API только на loopback VPS;
- передавать source/logo без Telegram bot token;
- принимать только PNG result с ограничением размера;
- добавить standalone Windows worker, совместимый с текущим Krita plugin protocol;
- возвращать задачи в очередь после истечения lease;
- сохранить локальный Krita bridge как rollback;
- добавить документацию и тесты.

### Критерии готовности

- Windows не получает `BOT_TOKEN`, `DATABASE_URL` и provider keys;
- worker API требует bearer token не короче 32 символов;
- job routes дополнительно требуют worker ID и одноразовый lease;
- порт Compose публикуется только на `127.0.0.1`;
- worker создаёт локальный request schema version 2 для неизменённого Krita plugin;
- heartbeat продлевает lease;
- истёкший lease возвращает revision в `pending`;
- результат принимается только как PNG и сохраняется атомарно;
- remote mode выключен по умолчанию;
- tests, type check, Docker build, notes contract и backup restore drill проходят.

### Риски и ограничения

- SSH-туннель и Krita должны быть запущены на Windows;
- GUI/Krita Python API не проверяются в CI;
- один worker обрабатывает одну задачу одновременно;
- первый production запуск требует живого end-to-end smoke;
- автоматическая установка Windows Scheduled Task остаётся отдельным эксплуатационным шагом.

## После завершения

### Фактически сделано

- добавляется migration lease/heartbeat и registry `krita_remote_workers`;
- добавляется remote repository с claim, heartbeat, fail и stale requeue;
- добавляется loopback HTTP API с bearer + per-job lease;
- source и custom logo выдаются только владельцу действующего lease;
- PNG result сохраняется атомарно и передаётся существующему preview lifecycle;
- remote runtime подключается через installer без переписывания Telegram watermark UI;
- standalone Windows worker использует только Python standard library;
- worker создаёт локальный schema v2 request для существующего Krita plugin;
- добавляются PowerShell launcher, README и unit/deployment tests;
- server env и Compose получают remote-настройки, выключенные по умолчанию.

### Миграции и совместимость

Добавляется неизменяемая миграция `z014_krita_remote_workers.sql`. Существующие watermark jobs и revisions остаются совместимыми. При `KRITA_REMOTE_WORKER_ENABLED=false` используется прежний локальный bridge. Remote mode требует одновременно `KRITA_WATERMARK_ENABLED=true`.

### Проверки

До merge выполняются:

- unit tests remote settings и local request contract;
- deployment contract loopback port и env defaults;
- PostgreSQL migration/backup restore drill;
- полный tests workflow;
- type check;
- Docker build;
- project notes contract.

### PR и commit

- PR: `#396` — «Отделить Krita в удалённый Windows worker»;
- ветка: `agent/krita-remote-worker`;
- проверяемый head фиксируется после CI.

### Незавершённое

- живой запуск SSH tunnel на Windows;
- проверка claim → Krita plugin → PNG upload → Telegram preview;
- установка worker как Windows Scheduled Task после smoke;
- перенос простых watermark-операций на Pillow/ImageMagick отдельным этапом.

### Следующий шаг

Получить зелёный CI, слить PR, затем после базового запуска VPS включить remote mode, открыть SSH-туннель и выполнить одну тестовую watermark-задачу до отключения локального Windows-бота.
