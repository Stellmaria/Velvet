# Память проекта Velvet

Дата актуализации: 2 августа 2026 года.

Этот файл хранит долгосрочную карту проекта и принятые архитектурные решения. Фактическое состояние продукта находится в `docs/development_status.md`, измерения — в generated inventories, подробности отдельных работ — в `docs/worklog/`, заметные изменения — в `CHANGELOG.md`.

## Источники истины

Порядок приоритета:

1. код, migrations, tests и слитые PR в `main`;
2. `docs/development_status.md`;
3. generated package/architecture/stability/shared inventories;
4. `docs/stabilization_policy.md`;
5. этот документ;
6. worklog и historical plans.

Старый документ не отменяет состояние `main`. При расхождении исправляется документ, а не реальность подгоняется под удобный абзац.

## Предметная граница продукта

Velvet Archive — owner-oriented архивный Telegram-бот для персонажей, историй, медиа, референсов, публикаций, аналитики, AI-проверок и Ауф-генераций.

Аукционные ставки, лоты, колоды и режимы торгов относятся к другому продукту.

## Режим стабилизации

До закрытия эксплуатационных ворот новый код допускается как улучшение существующего Velvet Archive:

- упрощение architecture/UI;
- повышение reliability, observability и isolation;
- перенос persistence/business logic в canonical boundaries;
- provider, queue, retry, delivery и payment hardening;
- staging, backup/restore, metrics, tests и docs;
- удаление compatibility и physical package debt.

Новая несвязанная предметная механика откладывается.

# Линия A. Основное развитие текущего Velvet Archive

## Фазы 1–6. Функциональная основа

Статус: завершены.

Архив, персонажи, истории, референсы, публикации, аналитика, quality/media sets, backup, diagnostics и owner operations работают и покрыты tests.

## Фаза 7. Модульная архитектура

Статус: логические boundaries и package-wide governance введены, физическая структура переходная.

Созданы и используются:

- application layer;
- domain repositories/services;
- infrastructure adapters;
- Telegram presentation root и четыре Router bundles;
- core config/access contracts;
- WorkerManager и lifecycle boundaries;
- package-wide AST inventory и mandatory exemption registry.

Не завершено физически:

- 113 root modules, из которых 110 non-facade должны мигрировать bounded families по #463;
- startup graph из 28 side-effect installers по #455;
- часть Ауф/provider/delivery/UI logic остаётся в `app/*_install.py`;
- 546 registered package fingerprints должны уменьшаться owner-by-owner, а не скрываться обновлением baseline.

## Фазы 8–11. Управление и production foundation

Статус кода: завершены.

- Supervisor, restart/update/rollback и Codex workflow;
- owner application use cases и Error Center;
- Python 3.13, PostgreSQL 16, Docker и healthcheck;
- automated restore drill, release/tag workflows;
- project notes contract;
- SHA-guarded branch maintenance;
- package architecture drift gate.

Живая Windows-проверка Supervisor остаётся обязательством #409.

## Фазы 12–17. Архитектурная очистка P1

Статус исторических срезов: завершены.

Закрыты прежние controller/SQL/repository boundaries, но формулировка «опасные runtime monkeypatch-мосты удалены» больше не является общей истиной: новый installer graph Ауф/media содержит зарегистрированный runtime assignment debt. Его target cleanup описан в #455/#457/#458/#459 и измеряется package exemptions.

## Фаза 18. Публичная граница PostgreSQL

Статус: завершена.

- внешний `Database._require_pool()` debt: 0/0;
- новые private pool accesses блокируются CI;
- repository inventory: 41 modules, 34 domain + 7 infrastructure;
- central/root repositories: 0.

## Фаза 19. Velvet AI operations

Статус: завершена для существующих quality operations.

Дальнейшая работа относится к metrics, provider live validation, performance и durable execution, а не к новой предметной области.

## Фаза 20. Удалённая эксплуатация Supervisor

Статус кода: завершён, live Windows acceptance не завершён.

Код содержит safe console, fast-forward update, tests, rollback, lock, healthcheck, external bootstrap и Telegram operation report. Проверка self-restart/update-and-restart выполняется по #409.

## Ауф: текущая продуктовая линия

Слито в `main`:

- canonical wallet/runtime/photo/user portal;
- active Telegram protocol Ауф;
- persistent identifier migration;
- GRS/Kie routing, retries, queue, charging и reconciliation;
- recovery готового provider result без новой платной генерации;
- retail price versions и фиксированные рублёвые packages;
- user registry и команды `/velvet_grant`, `/velvet_user`, `/velvet_users`;
- privacy boundary системных референсов.

Target architecture ещё не достигнута:

- #455 — explicit composition;
- #457 — durable unified delivery pipeline;
- #458 — portal/UI в application/presentation;
- #459 — provider adapters/routing/retry.

PR #450/#456 считаются временной stabilization delivery, а не конечным design. Package gate #460 завершён и измеряет debt, но не подменяет перечисленные migrations.

Historical migrations и dual-read `meow_*` aliases остаются до live retirement #438. Новые `meow_*` identifiers запрещены.

# Линия B. Velvet AI / Qwen

Статус фаз 1–8: завершены.

1. Проверка качества изображения.
2. Сравнение с референсом.
3. Целостность медиасетов.
4. Калибровка.
5. Единый AI-интерфейс.
6. Промт против результата.
7. Палитра и композиция.
8. Оформление Velvet Anatomy.

Следующие обязательства: live provider matrix #412, execution/cost metrics и heavy-runtime reliability.

# Линия C. Исторический план раннего рефакторинга

Этот heading сохранён для project CI. Ранний план фаз 1–11 находится в `docs/development_phases_analytics.md` и не является источником текущего статуса. Historical Ollama/local RP инструкции не считаются рекомендуемой production architecture; cloud RP acceptance ведётся отдельной задачей #413.

# Линия D. Стабильность P2

Статус: завершена.

Generated baseline:

- broad exception boundaries: 102;
- approved boundaries: 102;
- unresolved boundaries: 0;
- callback handlers: 132;
- late/missing callback acknowledgments: 0.

Широкие catches допускаются только на проверенных внешних boundaries с logging/compensation и явным `CancelledError` propagation.

# Линия E. Организация структуры P3

## P3A. Синхронизация источников истины

Статус: завершено PR #476 / issue #425; дальше обновляется вместе с `main`.

Canonical docs обязаны отличать shipped code от live obligations и temporary stabilization от target architecture.

## P3B. Telegram Router bundles

Статус: завершено.

- четыре ordered bundles;
- 84 active Router imports;
- duplicate registrations: 0;
- legacy handler imports: 0;
- catch-all order защищён AST tests.

## P3C. Физический перенос presentation

Статус: active legacy handlers/aliases удалены.

Новый долг находится не в старом `handlers`, а в large presentation/app modules и private cross-module contracts.

## P3D. Compatibility retirement

Статус старого handler compatibility layer: завершено.

Остаются 8 explicit runtime compatibility components: 7 pre-import и 1 post-import. Каждый должен получить permanent registration либо removal regression.

## P3E. Repository layout

Статус: завершено.

- repository modules: 41;
- domain repositories: 34;
- infrastructure adapters: 7;
- central/root repositories: 0.

## P3F. Статическая типизация

Первый bounded mypy gate действует. Scope расширяется постепенно; repository-wide strict mode одним изменением запрещён.

## P3G. Package-wide architecture drift gate

Статус: завершено issue #460 / PR #478 после зелёного merge.

Current reproducible baseline:

- 631 production modules;
- 136 683 LOC;
- 28 ordered startup installer stages;
- 546 registered file/category fingerprints;
- 546 complete exemptions;
- 0 unregistered fingerprints;
- 0 stale exemptions.

Scanner покрывает layers/targets, imports, aiogram boundaries, SQL/acquire, dynamic imports, foreign assignments, installers, `_INSTALLED`, package `__getattr__`, Any/cast/type-ignore, module/function size, handlers, env/polling и worker observations. Root/shared fingerprints связываются с existing inventories. Новый debt невозможно добавить тихим изменением внутри существующего файла: изменится fingerprint и CI потребует issue-backed exemption.

## Shared/private contract inventory

Package-wide shared inventory текущего baseline:

- 631 production Python files;
- 3597 functions;
- 182 registered private cross-module accesses;
- 0 blocking known private contracts;
- 62 exact, 97 normalized и 9 semantic duplicate groups.

Canonical helpers уже созданы, но transitional debt закрывается family-by-family по #419/#455/#457/#458/#459. Package gate отслеживает fingerprint shared-private baseline и не позволяет изменить его незаметно.

## Hermes Brain и сущности

Канонический cognitive control plane хранится в Obsidian-compatible
`brain-vault/`, но не заменяет GitHub, runtime DB, task ledger или secrets
store. Четыре сущности имеют отдельные manifest profiles: Каэль, Velvet Coder,
Макс и Velvet Librarian.

Действующие архитектурные решения:

- Каэль является единственным control plane и маршрутизирует fixed handoff;
- SOUL, AGENTS, shared context/cache/memory policies, bounded seeds и skills
  компилируются детерминированно для одной сущности;
- Codex получает global `$CODEX_HOME/AGENTS.md` из SOUL + project rules + memory,
  а не неиспользуемые соседние Markdown-файлы;
- Velvet и Max имеют отдельные CODEX_HOME/workspaces/skills/manifests;
- Librarian остаётся local-only deny-all и только предлагает memory candidate;
- долговременная запись проходит Kael review и coder PR;
- `context-manifest.json`, preflight и smoke подтверждают role/project и SHA-256;
- runtime memory seed никогда не перезаписывает живую memory.

Код и CI не означают server rollout. Фактическая установка выполняется после
merge через разрешённый `reconcilectl` и закрывается live context/auth/health
smoke.

# Открытые обязательства

## Кодовые P0/P1

1. #455 — explicit composition root.
2. #457 — unified durable media delivery.
3. #458 — canonical Ауф application/presentation boundaries.
4. #459 — provider adapters/routing/retry.
5. #463 — root module migration.
6. #419 — shared/private helper burn-down.

## На целевых средах

1. #407 — Linux VPS production cutover.
2. #409 — Supervisor Windows self-restart/update-and-restart.
3. #410 — post-deploy owner/workspace/AI/Ауф smoke.
4. #411 — staging bot/database.
5. #412 — live provider routes, limits, credits и result contracts.
6. #408 — encrypted offsite backup и independent restore.
7. #438 — live compatibility retirement.
8. Выполнить Hermes Brain reconcile после merge и подтвердить Kael/coder/
   Librarian context manifests в живых контейнерах.

# Стабилизационные ворота

Закрыты кодом/CI:

- private pool debt 0/0;
- P2 unresolved debt 0;
- legacy handler aliases 0;
- repository root/central debt 0;
- generated navigation violations 0;
- blocking known private helper contracts 0;
- safe branch maintenance #461;
- canonical docs sync #425;
- package-wide architecture drift gate #460;
- unregistered/stale package architecture fingerprints 0/0.

Не закрыты эксплуатационно:

- Windows Supervisor acceptance;
- staging и production cutover;
- live provider/payment/smoke matrix;
- encrypted offsite backup;
- unified durable delivery/composition;
- runtime/cost metrics.

# Правило выбора следующей задачи

Перед работой агент обязан:

1. определить issue и точный bounded slice;
2. проверить предметную границу;
3. прочитать current status/inventories/worklog;
4. определить измеримые критерии и removal condition;
5. не смешивать behavior change и physical migration без необходимости;
6. провести tests/CI и зафиксировать PR/commit;
7. оставить явный остаток и следующий шаг.

Любое изменение registered package debt должно уменьшать/удалять fingerprint либо сопровождаться новым issue-backed exemption. Простое обновление generated baseline ради зелёного CI не считается архитектурной работой.

Живая проверка, которую CI не способен выполнить, не помечается завершённой по факту существования кода.

## Актуализация inventory после pricing-среза 1 августа 2026

Воспроизводимый shared-contract срез после добавления закрытого pricing UI:

- production Python files: **641**;
- inventoried functions: **3685**;
- registered transitional private accesses: **186**;
- blocking known private contracts: **0**;
- целевая консолидация временных delivery/UI layers остаётся в **#457**.

## Срез feature-ветки AUF от 4 августа 2026 года

Этот блок фиксирует воспроизводимые числа текущей feature-ветки PR #590. Он не означает merge, rollout или закрытие архитектурного долга.

- production Python files: **646**;
- inventoried functions: **3725**;
- registered transitional private accesses: **187**;
- blocking known private contracts: **0**;
- package production modules: **646**;
- package production LOC: **141648**;
- registered package architecture fingerprints: **548**.

Переходные media delivery и provider-routing слои по-прежнему требуют burn-down в #457 и #459.

<!-- issue-459-shared-baseline -->
Provider adapter baseline: 648 production Python files, 3748 functions, 170 registered private accesses, 0 blocking contracts.
<!-- /issue-459-shared-baseline -->

<!-- gpt-image-2-pr-645-architecture-slice -->
## Срез feature-ветки GPT Image 2 от 5 августа 2026 года

Дата среза: `2026-08-05`.

Контракт стабильного релиза: `v1.3.0`.

Этот блок фиксирует воспроизводимые числа PR #645 и не означает production rollout или закрытие переходного долга:

- package production modules: **651**;
- inventoried functions: **3748**;
- registered transitional private accesses: **170**;
- blocking known private contracts: **0**;
- целевая консолидация delivery и provider-routing слоёв остаётся в **#457** и **#459**.
<!-- /gpt-image-2-pr-645-architecture-slice -->
