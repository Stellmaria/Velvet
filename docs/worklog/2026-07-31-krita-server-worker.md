# 2026-07-31 — Krita worker на Linux VPS

- Дата: 2026-07-31
- ID: krita-server-worker
- Линия/фаза: server migration / watermark runtime
- Статус: `частично`
- Ветка: `agent/krita-server-worker`
- Базовый commit: `1a80077a6d4c8a7ef46b2c4464b51af7a0aeb75d`

## Перед началом

### Цель

Убрать обязательную зависимость production watermark-процесса от включённого Windows-ПК. Krita должна работать на Linux VPS как изолированный локальный worker и использовать существующий файловый bridge без нового внешнего API.

### Исходный контекст

Watermark domain уже использует PostgreSQL revisions, безопасный файловый bridge, Telegram preview и финальное подтверждение. После переноса основного бота на Linux существующий локальный режим Krita остался привязан к Windows, а добавленный remote worker всё равно требовал включённый домашний компьютер, SSH-туннель и отдельный процесс.

### Планируемый объём

- добавить отдельный серверный образ Krita;
- запускать GUI-приложение внутри виртуального X-сервера;
- предварительно установить и включить существующий Python plugin;
- подключить Krita к тому же runtime bridge, что использует bot container;
- изолировать worker от сети и production-секретов;
- добавить healthcheck, systemd lifecycle и установщик;
- встроить локальный server mode в штатный production deploy;
- добавить настоящий end-to-end smoke через plugin protocol;
- сохранить remote Windows worker как rollback.

### Критерии готовности

- Krita запускается на Ubuntu VPS без физического дисплея;
- plugin `velvet_logo` загружается автоматически;
- bot и Krita видят одинаковый `/app/runtime/krita`;
- контейнер Krita не получает `.env.server`, Telegram token, DATABASE_URL или provider keys;
- контейнер не имеет сети и дополнительных Linux capabilities;
- healthcheck подтверждает процесс, plugin config и доступность bridge;
- smoke создаёт настоящий request schema v2 и получает корректный PNG;
- production deploy автоматически поднимает или останавливает server worker согласно env;
- Windows worker не запускается одновременно с server worker;
- CI собирает новый образ и проверяет deployment contracts.

### Риски и ограничения

- Krita остаётся GUI-приложением и требует Xvfb и session D-Bus;
- реальный Krita Python API нельзя полностью подтвердить unit-тестами;
- первая сборка образа на VPS будет заметно тяжелее обычного bot image;
- software OpenGL может увеличить CPU и память на больших изображениях;
- окончательная готовность требует live smoke на VPS и одной задачи через Telegram UI;
- server и remote worker нельзя включать одновременно.

## После завершения

### Фактически сделано

- добавлен `Dockerfile.krita-server` на Ubuntu 24.04;
- установлены Krita, Xvfb, session D-Bus и software OpenGL runtime;
- worker запускается под UID/GID `10001`;
- plugin `velvet_logo` устанавливается в `pykrita` и включается через `kritarc`;
- добавлен Compose profile `watermark`;
- единственный постоянный mount — общий `${VELVET_DATA_DIR}/runtime:/app/runtime`;
- добавлены `network_mode: none`, `cap_drop: ALL` и `no-new-privileges`;
- добавлен process/plugin/bridge healthcheck;
- добавлен реальный end-to-end smoke с временным PNG, schema v2 request и PNG output validation;
- добавлены `velvet-krita.service`, одношаговый установщик и reusable health wait;
- production deploy выбирает local server mode по сочетанию watermark/remote flags;
- добавлены CI build, deployment contract tests и отдельный runbook.

### Миграции и совместимость

Новых SQL-миграций нет. Существующие watermark jobs, revisions и файловый protocol не изменяются. Режимы совместимы следующим образом:

- local server: `KRITA_WATERMARK_ENABLED=true`, `KRITA_REMOTE_WORKER_ENABLED=false`;
- remote Windows: `KRITA_WATERMARK_ENABLED=true`, `KRITA_REMOTE_WORKER_ENABLED=true`;
- disabled: `KRITA_WATERMARK_ENABLED=false`.

Remote Windows worker и локальный server worker используют существующие контракты и остаются взаимозаменяемыми эксплуатационными режимами.

### Проверки

До merge выполняются:

- `bash -n` для новых и изменённых deployment scripts;
- Compose config с profile `watermark`;
- `pytest tests/test_krita_server_deployment_contract.py`;
- полный tests workflow;
- type check;
- project notes contract;
- сборка `Dockerfile.krita-server`;
- сборка существующего bot image.

После merge на VPS обязательны Docker healthcheck, `deploy/server/krita-smoke.sh` и одна задача через Telegram UI.

### PR и commit

- PR: `#487` — «Перенести Krita watermark worker на Linux VPS»;
- ветка: `agent/krita-server-worker`;
- базовый commit: `1a80077a6d4c8a7ef46b2c4464b51af7a0aeb75d`;
- проверяемый head фиксируется после завершения CI.

### Незавершённое

- получить зелёные tests/type check/project notes/Docker build;
- собрать образ непосредственно на VPS `144.31.165.142`;
- запустить `sudo bash deploy/server/install-krita-server.sh`;
- выполнить live smoke на серверном Docker storage;
- проверить одну watermark-задачу через Telegram UI;
- наблюдать память и CPU на нескольких больших изображениях.

### Следующий шаг

Исправить оставшиеся CI-замечания, затем после merge обновить `/srv/velvet`, запустить серверный установщик и подтвердить реальную обработку изображения до отключения Windows Krita worker.
