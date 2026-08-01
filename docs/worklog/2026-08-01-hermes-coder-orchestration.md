# 2026-08-01 — Оркестрация Hermes coder-агентов

- Дата: `2026-08-01`
- ID: `hermes-coder-orchestration`
- Линия/фаза: `server operations`
- Статус: `в работе`
- Ветка: `agent/hermes-coder-orchestration`
- Базовый commit: `1d763e9217204841a0b7ed0437434737f4cbae27`

## Перед началом

### Цель

Связать главный `@VelvetHermesBot` с изолированными coder-агентами Velvet и Max, чтобы оператор мог безопасно передавать задачи, отслеживать Runs API, проверять созданные pull request и CI, а также отправлять владельцу Telegram-отчёты. Runtime-операции и merge должны по-прежнему требовать явного разрешения владельца.

### Исходный контекст

PR `#529` добавил главному Hermes фиксированный gateway для `status/logs/start/restart/update/rollback`. PR `#500` ранее разделил coder-агентов по репозиториям и выдал им отдельные workspaces, GitHub credentials и read-only DB роли. Между главным Hermes и coder-агентами отсутствовали очередь заданий, внутренний transport, журнал состояния, ожидание terminal результата и обратная доставка отчёта.

### Планируемый объём

- добавить отдельный `hermes-coder-router` без host mounts и runtime credentials;
- подключить coder Runs API только через internal Docker network;
- добавить `coderctl.py` с submit/status/wait/list/stop и постоянным журналом;
- зафиксировать project routing Velvet/Max и строгий контракт задания;
- расширить managed SOUL главного Hermes и обоих coder-агентов;
- дождаться terminal результата аварийного Hermes run;
- отправлять итог разбирательства через существующий Telegram notifier Supervisor;
- добавить installer, runbook и regression tests.

### Критерии готовности

- главный Hermes не видит coder API keys;
- router не получает Docker socket, systemd, production checkout, `.env` или supervisor tokens;
- Velvet-задача не может быть направлена Max-coder и наоборот;
- coder создаёт ветку/PR, но не может выполнять merge или deployment;
- task/run сохраняются в постоянном журнале;
- автоматический Velvet-инцидент завершается Telegram-отчётом;
- unit, type, project notes, Docker и Compose checks проходят.

### Риски и ограничения

- Runs API coder-агентов должен слушать private network, поэтому `API_SERVER_HOST` меняется с loopback на `0.0.0.0`, но host ports не публикуются;
- новый internal network является единственным маршрутом router → coders;
- автоматический watcher Max не входит в Velvet runtime и потребует связанного PR в Max;
- ошибки модели или coder не являются основанием для merge/update без независимой проверки;
- автоматическая передача инцидентов остаётся выключенной до server-side `HERMES_INCIDENT_ENABLED=true`.

## После завершения

Статус: `в работе`.

### Фактически сделано

- добавлен strict HTTP router с фиксированными проектами и Runs API routes;
- добавлен `coderctl.py` с атомарным JSON ledger и redaction;
- coder API вынесен в отдельную internal network без published ports;
- добавлены разные `API_SERVER_KEY` и preflight-проверки;
- главный Hermes получил project routing, PR/CI verification и owner-approval contract;
- coder SOUL требует одну ветку, один PR и структурированный terminal report;
- Velvet incident client ожидает terminal Hermes run и возвращает очищенный результат;
- Supervisor notifier отправляет terminal report владельцу;
- добавлен идемпотентный orchestration installer и runbook;
- добавлены unit/security/deployment contract tests.

### Изменённые модули и контракты

- `deploy/hermes-operator/coder_router.py` — изолирующий Runs API router;
- `deploy/hermes-operator/coderctl.py` — CLI и журнал задач;
- `deploy/hermes-operator/compose.yaml` — router service;
- `deploy/hermes-coders/compose.yaml` — private agent control network;
- `deploy/hermes-coders/preflight.py` — разные API keys;
- `deploy/hermes-orchestration/install.sh` — production installer;
- `velvet_supervisor/hermes_incident.py` — terminal polling/callback;
- `velvet_supervisor/runtime_extended.py` — Telegram terminal report;
- `tests/test_hermes_coder_orchestration.py` и `tests/test_supervisor_hermes_incident.py` — regressions.

### Миграции и совместимость

SQL-миграций нет. Production базы и bot runtime не изменяются. Existing Telegram/GitHub/model credentials coder-агентов сохраняются. Installer добавляет только отдельные coder API keys и router env.

### Проверки

- локальный AST/compile новых Python-модулей;
- локальный `bash -n` installer;
- unit tests router, ledger, redaction, terminal incident callback;
- полный GitHub Actions CI после публикации draft PR.

### Незавершённое

- синхронизировать ветку с текущим `main`;
- завершить preflight вызов в installer;
- открыть draft PR и исправить CI;
- после merge установить на VPS и выполнить health smoke;
- отдельным PR добавить автоматический incident watcher Max.

### Следующий шаг

Завершить installer/runbook, открыть draft PR и довести все обязательные проверки до зелёного состояния без включения production orchestration до merge.
