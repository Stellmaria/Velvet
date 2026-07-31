# 2026-07-31 — Krita worker на Linux VPS

- Дата: 2026-07-31
- ID: krita-server-worker
- Линия/фаза: server migration / watermark runtime
- Статус: `частично`
- Ветка: `agent/krita-server-worker`

## Цель

Убрать обязательную зависимость production watermark-процесса от включённого Windows-ПК. Krita должна работать на VPS как изолированный локальный worker и использовать существующий файловый bridge без нового сетевого API.

## Реализовано

- отдельный образ `Dockerfile.krita-server` на Ubuntu 24.04;
- Krita 5.2.2 из Ubuntu Noble, `Xvfb`, session D-Bus и software OpenGL;
- запуск под UID/GID `10001`, как у bot container;
- предварительно установлен и включён `velvet_logo` Python plugin;
- профиль Compose `watermark`;
- общий `${VELVET_DATA_DIR}/runtime:/app/runtime` только для bot и Krita;
- `network_mode: none`, `cap_drop: ALL`, `no-new-privileges`;
- process/plugin/bridge healthcheck;
- реальный end-to-end smoke request с PNG output validation;
- systemd unit `velvet-krita.service`;
- одношаговый установщик `deploy/server/install-krita-server.sh`;
- автоматическое включение серверной Krita в production deploy при локальном watermark mode;
- CI build и deployment contract tests;
- отдельный runbook.

## Режимы

- local server: `KRITA_WATERMARK_ENABLED=true`, `KRITA_REMOTE_WORKER_ENABLED=false`;
- remote Windows: `KRITA_WATERMARK_ENABLED=true`, `KRITA_REMOTE_WORKER_ENABLED=true`;
- disabled: `KRITA_WATERMARK_ENABLED=false`.

Локальный серверный и удалённый Windows worker не запускаются одновременно.

## Безопасность

Контейнер Krita не получает `.env.server`, Telegram token, DATABASE_URL или provider keys. Сеть полностью выключена. Единственный постоянный mount — общий runtime, необходимый для bridge protocol.

## Проверки до merge

- `bash -n` всех новых deployment scripts;
- Compose config с профилем `watermark`;
- `pytest tests/test_krita_server_deployment_contract.py`;
- сборка `Dockerfile.krita-server`;
- существующие tests/type check/notes contract.

## Незавершённое

- сборка образа непосредственно на VPS `144.31.165.142`;
- запуск `sudo bash deploy/server/install-krita-server.sh`;
- live smoke на серверном Docker storage;
- одна тестовая watermark-задача через Telegram UI;
- наблюдение памяти и CPU на нескольких больших изображениях.

## Следующий шаг

После зелёного CI слить PR, обновить `/srv/velvet`, запустить установщик и проверить одну задачу через Telegram до отключения Windows Krita worker.
