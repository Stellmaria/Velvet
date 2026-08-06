# Arthur Librarian Phase 2

- Дата: 2026-08-06
- ID: phase2-arthur-20260806
- Линия/фаза: Arthur Librarian / Phase 2
- Статус: частично
- Ветка: feat/arthur-librarian-phase2
- Базовый commit: 5cd04ae20bb0bb6099cc5be920eb1f844cf5b54d
- Синхронизировано с main: 0022b7404b9419ed73869f4a4e9c6a3d53bd8bd8

## Перед началом

### Цель

Выделить существующий Storage Librarian в отдельный owner-only Telegram runtime Arthur без пользовательского UX Librarian в основном Velvet bot.

### Исходный контекст

- issue #586 является источником acceptance criteria;
- Phase 1 text-only hardening уже находится в `main`;
- production smoke Storage #2168 завершён отдельно и не повторяется в этой GitHub-сессии;
- vision runtime и image-byte pipeline находятся вне scope и ведутся в #630;
- Telegram `file_id` привязан к bot identity, поэтому Arthur не может безопасно получить токен Velvet или напрямую скачивать существующие Storage parts.

### Планируемый объём

- отдельные Arthur settings, owner allowlist, dispatcher, polling lifecycle и команды;
- private authenticated Storage gateway, который единственный получает токен Velvet для чтения существующих Telegram Storage parts;
- gateway-backed analysis/download path для Arthur;
- перенос Librarian-команд из router основного Velvet bot;
- isolated Compose profile без host ports, Docker socket, GitHub credentials, shell/systemd tools и cloud fallback;
- unit, integration-contract, Docker/security и command-registration tests;
- runbook и env contracts.

### Критерии готовности

- Arthur использует отдельный `ARTHUR_BOT_TOKEN` и отдельный allowlist;
- token reuse между Arthur и Velvet отклоняется fail-closed;
- `/analyze ID`, `/result ID`, `/ask`, `/digest`, `/queue`, `/download ID`, `/status`, `/start` и `/help` зарегистрированы только в Arthur;
- manual analysis проходит Arthur -> Storage gateway -> private Ollama, answer path -> dedicated Hermes;
- `STORAGE_LIBRARIAN_AUTO_ENQUEUE=false` остаётся обязательным default;
- main owner router не регистрирует Librarian UX;
- Compose не публикует Arthur, gateway, Ollama или Hermes ports на host;
- полный CI и exact-head review зелёные до merge.

### Риски и ограничения

- production rollout, bot token creation/change, restart, reconcile и live Telegram smoke не выполняются без отдельного эксплуатационного шага;
- stale-running job recovery не смешивается с Phase 2;
- `/cancel` не добавляется без безопасного cooperative cancellation contract;
- временные production workaround’ы не удаляются;
- массовая очередь и AFK не включаются.

### Архитектурное обоснование стабилизации

1. Улучшается существующая функция Storage Librarian.
2. Owner UX и credentials становятся изолированнее, а download path получает явную private service boundary.
3. Новая предметная область не добавляется: меняется delivery/runtime существующего archive analysis.
4. Улучшение проверяется unit/integration/Docker/security tests и последующим отдельным production smoke.
5. Сохраняются repository/use-case boundaries, protected kinds, manual-first и local-only model execution.

## После завершения

### Фактически сделано

- добавлены отдельные `ArthurSettings` и `ArthurStorageGatewaySettings` с fail-closed проверками token reuse, allowlist, gateway credential и manual-first режима;
- реализован отдельный Telegram polling runtime Arthur и owner-only middleware;
- добавлены команды `/start`, `/status`, `/analyze`, `/result`, `/ask`, `/digest`, `/queue`, `/download` и `/help`;
- `/status` выполняет живые probes private gateway, Ollama `/api/tags`, наличия configured text alias и Librarian Hermes `/health`;
- реализован exact-object claim для ручного `/analyze ID`, чтобы команда не забирала произвольную queued job;
- повторный `/analyze ID` не переводит активную `running` job обратно в `queued`;
- добавлен private authenticated Storage gateway, который единственный получает Velvet `BOT_TOKEN` и проверяет размер/SHA загруженного объекта;
- анализ Arthur использует существующий strict-schema Ollama client, ответы по индексу используют отдельный Librarian Hermes client;
- executable-регистрация Librarian UX удалена из основного owner router Velvet;
- добавлен opt-in Compose profile `arthur` без host ports, Docker socket, GitHub credentials и cloud provider keys;
- gateway и Arthur стартуют последовательно с `--no-deps`, не пересоздавая уже healthy Ollama/Hermes;
- installer адресно создаёт Arthur data dir для UID/GID `10001:10001` без recursive `chown`;
- startup smoke подтверждает authenticated Arthur -> gateway -> PostgreSQL route, heartbeat и Arthur -> private Ollama strict-schema path;
- добавлены unit, security, deployment, owner-help и command-registration contracts;
- добавлены env template и production runbook.

### Миграции и совместимость

- новых PostgreSQL migrations нет;
- используются существующие `telegram_storage_analysis_jobs` и `telegram_storage_analysis` contracts;
- существующие Storage Librarian application/domain modules сохранены для совместимости, но основной Velvet router больше не регистрирует их пользовательские команды;
- Arthur profile остаётся opt-in: без отдельного token, gateway credential и owner allowlist текущий Librarian lifecycle не запускает новые сервисы;
- branch merged с актуальным `main` commit `cf4df6868ac6e4c7ccfba6d87909fd782892cbc4`;
- production workarounds и текущий manual-first режим не изменялись.

### Проверки

- Python syntax compilation новых модулей и Compose YAML parsing выполнены до публикации;
- ранний GitHub Actions type check прошёл;
- исправлены подтверждённые ранними checks требования worklog, owner-help isolation, runtime-only test dependencies, security scan и package inventory;
- canonical package architecture inventory заново сгенерирован на объединённом Arthur + current main дереве и прошёл штатный `--check --label p1-package-architecture-baseline`;
- canonical status, project memory и architecture audit синхронизированы с baseline `659 / 3748 / 170 / 0`, а `tests.test_canonical_docs_sync` прошёл;
- dependency-free final baseline workflow синхронизировал все package inventory counters, исключил команды отдельного Arthur runtime только из Velvet route inventory и удалил временный workflow после зелёной проверки;
- Telegram polling и report publisher перенесены из `application` в `presentation`, поэтому application layer остаётся framework-neutral и не импортирует `aiogram`;
- финальные boundary и canonical workflows прошли зелёными и удалили собственные временные workflow-файлы до protected CI;
- branch пересобрана поверх current main `0022b7404b9419ed73869f4a4e9c6a3d53bd8bd8` с сохранением honest GPT Image export contract PR #659;
- полный protected-branch CI и exact-head review являются последним merge gate для PR #657;
- production Telegram/PostgreSQL smoke сознательно не выполнялся в GitHub-сессии.

### PR и commit

- PR: #657 `Arthur Librarian Phase 2: dedicated Telegram runtime`;
- ветка: `feat/arthur-librarian-phase2`;
- merged implementation parent: `c6166dba9f9ebc0764f4b7c3c8cc0d4fe3a698ff`;
- итоговый exact head и squash merge commit фиксируются GitHub после зелёных required checks.

### Незавершённое

- создание и внесение production `ARTHUR_BOT_TOKEN`;
- штатный update/reconcile rollout и live smoke на одном безопасном Storage object;
- подтверждение production-результата в PostgreSQL и runtime invariants;
- stale-running job recovery, controlled batches, AFK/mass enqueue и vision pipeline #630;
- удаление временных production workaround’ов.

### Следующий шаг

Пройти полный exact-head CI, проверить review threads и выполнить squash merge PR #657 в `main`. Production acceptance остаётся отдельным owner-controlled этапом.
