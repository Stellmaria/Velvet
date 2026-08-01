# Сессия: Hermes coder через Codex GPT-5.6

- Дата: 2026-08-02
- ID: 2026-08-02-hermes-codex-56-runner
- Линия/фаза: server operations / Hermes coder
- Статус: частично
- Ветка: infra/hermes-codex-56-runner
- Базовый commit: 0ad3e39e0607c55dc06fe4bdbb90ca3fdcaa779a

## Перед началом

### Цель

Перевести оркестрированные coder-задачи главного Hermes с Byesu-backed gateway на локальный OpenAI Codex CLI, авторизованный через ChatGPT-план владельца, сохранив отдельные проекты Velvet и Max, существующий Runs API и приватные Telegram Hermes gateway.

### Исходный контекст

До изменения `hermes-coder-velvet` и `hermes-coder-max` отправляли модельные запросы через Byesu. Сброс лимита ChatGPT/Codex на эти запросы не влиял. `hermes-coder-router` уже направлял задачи по фиксированному Runs API, вёл журнал и проверял PR/CI, поэтому внешний orchestration contract требовалось сохранить.

### Планируемый объём

- добавить отдельный Codex runner для каждого проекта;
- сохранить Runs API `capabilities`, `submit`, `status` и `stop`;
- разделить Codex coder и старые Telegram chat gateway;
- изолировать auth, workspaces, журналы и GitHub credentials;
- добавить установку, device login, preflight, runtime smoke и документацию;
- покрыть новую схему unit- и contract-тестами.

### Критерии готовности

- главный Hermes направляет coder-задачи в Codex CLI;
- разрешены только `gpt-5.6-luna`, `gpt-5.6-terra` и `gpt-5.6-sol`;
- Velvet и Max имеют отдельные `CODEX_HOME`, auth и workspaces;
- Codex не получает production Docker socket, systemd, production checkout или DB credentials;
- существующий router не требует изменения публичного контракта;
- CI проекта проходит;
- после merge выполнены device login, preflight и live smoke на VPS.

### Риски и ограничения

- device login требует интерактивного подтверждения владельца;
- ChatGPT/Codex usage limits являются общими для авторизованного плана;
- `GH_TOKEN` необходим внутри coder sandbox для branch, push и PR;
- live production smoke невозможно завершить до merge и серверной авторизации;
- изменения не должны прерывать существующие приватные Telegram coder-боты.

## После завершения

### Фактически сделано

- добавлены `codex_runner.py` и routed entrypoint;
- сохранён существующий Runs API и внутренние адреса router;
- старые Byesu-backed Telegram gateway выделены в `hermes-chat-velvet` и `hermes-chat-max`;
- созданы отдельные Codex services `hermes-coder-velvet` и `hermes-coder-max`;
- добавлены отдельные `CODEX_HOME`, workspaces, run journals и API keys;
- Codex CLI закреплён на версии `0.144.4`, release asset проверяется по SHA-256;
- добавлены `install-codex.sh`, `codex-login.sh`, `CODEX.md`, preflight и runtime smoke;
- секреты Telegram, Byesu, database и Runs API исключены из Codex shell;
- `GH_TOKEN` оставлен только для работы с ограниченным репозиторием;
- исправлена тестовая совместимость после обобщения `wait_for_gateway` в `wait_for_service`.

### Миграции и совместимость

Публичный Runs API и URLs `hermes-coder-*` сохранены. Существующие Telegram gateway не удалены, а переименованы в `hermes-chat-*`. Production deployment требует создания Codex homes и workspaces, двух device login и перезапуска coder/router services. Миграций PostgreSQL нет.

### Проверки

- локальный целевой набор Codex/Hermes contract-тестов: `24 tests, OK`;
- Python sources проходят compile/AST parse;
- Bash installers проходят `bash -n`;
- GitHub Actions PR #547: `type check` прошёл;
- первый CI run выявил устаревшее имя helper-функции в regression-тесте и несоответствие worklog-шаблону; оба замечания исправлены в ветке;
- актуальный полный CI должен пройти после публикации исправлений;
- live VPS smoke остаётся обязательным после merge и device login.

### PR и commit

- PR: #547 `Перевести Hermes coder на Codex GPT-5.6`;
- ветка: `infra/hermes-codex-56-runner`;
- commits: реализация и последующие CI-fixes в этой ветке.

### Незавершённое

- получить зелёный полный CI для актуального head PR #547;
- слить PR в `main`;
- обновить `/srv/velvet` на VPS;
- выполнить device login отдельно для Velvet и Max;
- выполнить preflight, runtime smoke и тестовую coder-задачу с созданием PR.

### Следующий шаг

После зелёного CI слить PR #547. Затем установить Codex runner на VPS, выполнить два device login и подтвердить live smoke до передачи реальных задач.
