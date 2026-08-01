# 2026-08-02 — Hermes coder через Codex GPT-5.6

- Дата: `2026-08-02`
- ID: `hermes-codex-56-runner`
- Линия/фаза: `server operations`
- Статус: `реализовано в ветке, production smoke ожидает merge и device login`
- Ветка: `infra/hermes-codex-56-runner`
- Базовый commit: `0ad3e39e0607c55dc06fe4bdbb90ca3fdcaa779a`

## Цель

Перевести задания главного Hermes на Codex CLI, авторизованный через ChatGPT-план владельца, чтобы использовать модели `gpt-5.6-luna`, `gpt-5.6-terra` и `gpt-5.6-sol`, сохранив изоляцию проектов Velvet/Max, текущую Runs API orchestration и отдельные Telegram Hermes gateway.

## Исходное состояние

До изменения `hermes-coder-velvet` и `hermes-coder-max` являлись Hermes gateway и отправляли модельные запросы на Byesu. Сброс лимита Codex/ChatGPT на них не влиял. Главный `hermes-coder-router` уже умел направлять задачи по фиксированным Runs API адресам, вести журнал, проверять PR и CI, поэтому менять внешний orchestration contract не требовалось.

## Реализовано

### Codex backend

Добавлен `deploy/hermes-coders/codex_runner.py`:

- совместимый Runs API: capabilities, submit, status и stop;
- запуск `codex exec --json --model ... --sandbox workspace-write`;
- разрешённый набор только из Luna, Terra и Sol;
- основная модель Terra;
- fallback между моделями только при rate/model/capacity error;
- один активный run на проект;
- атомарный журнал runs с режимом `0600`;
- timeout, process-group termination и stop endpoint;
- очистка секретов из логов и terminal output.

### Разделение сервисов

Старые Telegram gateway переименованы:

```text
hermes-chat-velvet
hermes-chat-max
```

Имена, на которые уже смотрит router, заняты Codex backend:

```text
hermes-coder-velvet
hermes-coder-max
```

Таким образом, главный Hermes начинает использовать Codex без изменения router URL, а приватные Telegram coder-боты сохраняются как отдельный Byesu-backed chat layer.

### Изоляция

Каждый Codex runner получает отдельные:

- `CODEX_HOME` и device-login auth;
- Git checkout;
- run journal;
- Runs API key;
- GitHub token;
- Docker service и resource limits.

Codex services не подключены к production DB networks, не имеют Docker socket, systemd, production checkout или host ports. Доступны только egress и internal `hermes-agent-control`.

### CLI и supply chain

`Dockerfile.coder` закрепляет Codex CLI `0.144.4`, скачивает официальный GitHub release asset и проверяет опубликованный SHA-256 digest. В образ также добавлены `bubblewrap`, `git` и `ripgrep`.

### Авторизация и установка

Добавлены:

- `install-codex.sh` для отдельных homes, workspaces, ключей и сборки;
- `codex-login.sh` для `codex login --device-auth` по каждому проекту;
- `CODEX.md` с production runbook.

Auth-файлы не копируются между проектами и должны иметь режим `0600`.

### Sandbox и секреты

Codex работает в `workspace-write`, без approval prompts. Network разрешён внутри отдельного coder-контейнера, поскольку агенту нужны GitHub push и PR operations.

Shell получает `GH_TOKEN`, но исключает:

- Runs API keys;
- Byesu keys;
- Telegram token;
- database credentials.

Apps/plugins/tool suggestions выключены, чтобы Codex не синхронизировал посторонние материалы в рабочий Git checkout.

## Проверки

Добавлены или обновлены:

- `tests/test_hermes_codex_runner.py` — model allowlist, fallback, JSONL parsing, redaction, private run journal и capabilities;
- `tests/test_hermes_coders_contract.py` — Compose isolation, отдельные workspaces/auth, pinned CLI, secret policy, device login и systemd order;
- `runtime_smoke.py` — Telegram gateway health, Codex login, CLI version, Luna/Terra/Sol capabilities, GitHub auth и dry-run push;
- `preflight.py` — отдельные keys/auth/workspaces, Git identity, sandbox/network policy и file modes.

Локально выполнены Python compile, Bash syntax и 19 новых/переписанных unit/contract тестов. Полный GitHub Actions CI будет доступен после создания pull request.

## Production-порядок после merge

```bash
cd /srv/velvet
sudo bash deploy/hermes-coders/install-codex.sh
sudo bash deploy/hermes-coders/codex-login.sh velvet
sudo bash deploy/hermes-coders/codex-login.sh max
sudo env HERMES_CODERS_ROOT=/srv/hermes-coders python3 deploy/hermes-coders/preflight.py
sudo systemctl restart hermes-coders.service
sudo systemctl restart hermes-coder-router.service
sudo env HERMES_CODERS_ROOT=/srv/hermes-coders python3 deploy/hermes-coders/runtime_smoke.py
```

## Незавершённое

- создать pull request и получить полный CI;
- после merge обновить VPS;
- выполнить два интерактивных device login;
- провести live Codex task smoke на Velvet и Max;
- проверить созданный test PR и только затем использовать backend для реальных задач.
