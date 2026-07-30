# Changelog

Все заметные изменения Velvet Archive фиксируются в этом файле. Подробная техническая история каждого среза хранится в `docs/worklog/`; changelog содержит только слитые изменения и не включает technical runner-PR.

## [Unreleased]

### Ауф: генерации, экономика и пользователи

- Добавлены canonical photo/video flows, queue lifecycle, wallet, charging, reconciliation и user portal.
- Активный Telegram protocol и пользовательский бренд переведены с Мяу на Ауф; persistent database/module identifiers мигрированы без переписывания historical migrations.
- Добавлена повторная доставка готового provider result без нового submit, attempt и списания; missing URLs могут восстанавливаться через provider task id.
- Реальная API-себестоимость отделена от пользовательской розничной цены.
- Добавлены versioned retail tariffs для текущих photo/video models и фиксированные рублёвые packages: 40/119 ₽, 100/269 ₽, 250/649 ₽, 500/1190 ₽, 1000/2290 ₽ и 2500/5490 ₽.
- Обычный пользователь больше не видит внутреннее USD-покрытие, provider cost и служебную наценку.
- Добавлены privacy-safe `telegram_users`/`telegram_user_events`, команды `/velvet_grant`, `/velvet_user`, `/velvet_users` и уведомления о заявках/начислениях.
- Системные референсы исключены из пользовательского выбора и остаются доступны только глобальному владельцу.
- Старые операции, счета и завершённые генерации не пересчитываются новыми тарифами.

### Shared Telegram contracts и architecture inventory

- Добавлен package `velvet_bot.presentation.telegram.shared` с typed contracts для safe edit, idempotent deletion, navigation, text chunking, media download и retry/backoff.
- Package-wide shared-contract inventory покрывает app/installers, routers и workers, direct imports, module attributes, assignments и near-duplicates.
- Known blocking private contracts мигрированы; Supervisor и Ауф editing families используют public adapters вместо private cross-module helpers.
- Generated baseline фиксирует 596 production Python files, 3306 functions, 136 registered transitional private accesses и 0 blocking known contracts.
- Exact/normalized/semantic duplicate groups фиксируются как 55/92/9 и имеют owner/target/retirement issue.

### P3 structure and canonical boundaries

- Root Telegram Router собирается четырьмя ordered domain bundles без direct `velvet_bot.handlers.*` imports.
- Все active legacy handler implementations и aliases удалены; production legacy-consumer baseline равен 0/0/0.
- Current Router inventory содержит 84 active imports и 0 duplicate registrations.
- Repository layout содержит 35 modules: 34 domain repositories и 1 PostgreSQL infrastructure adapter; central/root repositories отсутствуют.
- Private PostgreSQL pool access закрыт на 0 production references.
- Bounded mypy gate включён для transport-neutral scope и блокирует новые typing errors в выбранной границе.
- Canonical status, project memory и architecture audit синхронизированы с current `main`, а temporary installer/delivery stabilization отделена от target architecture.

### Telegram navigation and mobile UX

- Добавлен generated inventory всех production inline/reply keyboards.
- Current navigation baseline: 604 scanned Python files, 1024 inline buttons, 0 reply buttons и 0 violations.
- Компактные entity labels, двухколоночные rows и owner-home navigation унифицированы для Android и desktop Telegram.
- Динамические character/story/universe/analytics/publication labels ограничены без изменения callback semantics.

### Owner diagnostics and reliability

- Добавлен owner-only `Velvet Diagnostic Bundle v1` с redacted runtime, workers, Error Center incidents и bounded log tail.
- Добавлена автоматическая critical diagnostics с cooldown.
- Qwen retry сохраняет `media_ai_profiles.analysis` как валидный `JSONB NOT NULL`.
- Permanent oversized/no-preview calibrated AI skips логируются как `INFO`; реальные provider/database/filesystem failures остаются `WARNING/ERROR`.
- P2 stability inventory закрыт: 76 approved broad boundaries, 0 unresolved, 98 callback handlers и 0 late/missing acknowledgments.

### Safe branch maintenance

- Добавлен manual `branch maintenance` workflow для deterministic cherry-pick одного reviewed commit в allowlisted feature branch.
- Workflow требует exact target/source SHA, single-parent source, staged dry-run, полный unit test suite и повторную SHA-проверку перед обычным push.
- `main`/`master`, force-push, automatic merge и conflict resolution запрещены.
- Повторный запуск является auditable no-op, если source уже применён либо его patch эквивалентно присутствует.
- Добавлены runbook и CI allowlist для всех workflows с `contents: write`.

### Temporary stabilization and remaining target work

- PR #450/#456 recovery layers сохраняют готовые provider results при Telegram/CDN failures, но считаются временной stabilization до unified durable delivery #457.
- Startup всё ещё использует 27 side-effect installer stages; target explicit composition ведётся в #455.
- Ауф portal/UI, provider adapters, package-wide drift gates и root-module migration продолжаются в #458/#459/#460/#463.
- Historical `meow_*` migrations и dual-read FSM/transport compatibility остаются до live retirement #438; новые persistent `meow_*` identifiers запрещены.

## [1.3.0] - 2026-07-17

### Added

- Dockerfile для Velvet Bot на Python 3.13.
- Docker Compose с PostgreSQL 16, ботом и опциональной Ollama.
- Container healthcheck и отдельный CI workflow сборки Docker image.
- Автоматический restore drill: dump, новая база, полное восстановление, migrations и контроль данных.
- Еженедельная GitHub Actions проверка восстановления backup.
- Release workflow с проверкой соответствия Git tag и `APP_VERSION`.
- Transport-neutral `PublicationActions` и PostgreSQL integration tests основных production boundaries.
- Owner-only watermark contour через локальный Krita bridge.
- Постоянный журнал AI jobs, operational quality menu и reference/prompt/palette/formatting/media-set checks.
- Безопасная удалённая Supervisor console и внешний Windows bootstrap для self-restart/self-update.
- Project memory, worklog и CI project-notes contract.

### Changed

- Docker и CI используют PostgreSQL 16.
- Версия приложения переведена с `1.3.0-dev.1` на стабильную `1.3.0`.
- Analytics navigation вынесена в единый presentation contract.
- Publication center переведён на application coordinator.
- Analytics management, owner forms и multi-story boundaries разделены на canonical modules/repositories.
- Private PostgreSQL access последовательно мигрирован на public `Database.acquire()` и repositories.
- Режим стабилизации ограничивает новый код ускорением, упрощением, reliability, observability и operational readiness существующих функций.

### Fixed

- Backup/restore, publication, archive preview, notifications, AI jobs и media quality boundaries получили cancellation/error regression coverage.
- Telegram callback acknowledgment приведён к 0 late/missing handlers.
- Applied migrations защищены SHA-256 и duplicate-number checks.
- Stale Krita requests, unsafe output paths и outdated watermark revisions обрабатываются безопасно.
- Зависшие после restart AI jobs получают `interrupted`, а не остаются в бесконечном ожидании.
