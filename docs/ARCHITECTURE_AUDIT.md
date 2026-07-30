# Актуальный аудит архитектуры Velvet

Дата актуализации: 30 июля 2026 года.

Проверенный baseline `main`: `9a32e5f1118c89bff3c91f0d517c38bd8bad24e7`.

## Объём проверки

Проверены:

- application bootstrap и startup composition;
- Router bundles и порядок Telegram controllers;
- domain/application/infrastructure boundaries;
- PostgreSQL repositories и migrations;
- Ауф wallet, provider routing, charging, queue и delivery;
- shared/private cross-module contracts;
- runtime installers, foreign assignments и compatibility components;
- generated architecture, repository, navigation и stability inventories;
- Supervisor, branch maintenance, backup и CI contracts;
- canonical status documents и открытые operational gates.

## Итог

Velvet имеет рабочие логические domain/application/persistence boundaries, закрытый private-pool debt, централизованный Telegram root Router и нулевой active legacy-handler layer. Это реальное достижение, а не традиционное переименование папок с последующим объявлением победы.

Целевая архитектура при этом ещё не достигнута. Главный correctness-risk переместился в `velvet_bot/app` и media generation layers: startup собирается цепочкой side-effect installers, итоговые workers/controllers зависят от runtime assignments, а delivery распределена между canonical classes и временными hotfix/recovery layers.

## Воспроизводимый baseline

### Telegram composition

По `docs/architecture_layout_inventory.*`:

- root imports `velvet_bot.handlers.*`: **0**;
- ordered Router bundles: **4**;
- active Router imports: **84**;
- duplicate bundle registrations: **0**;
- legacy handler files: **0**;
- legacy handler implementations: **0**;
- handler compatibility facades: **0**;
- runtime compatibility components: **8**.

### Persistence layout

По `docs/repository_layout_inventory.*`:

- repository modules: **35**;
- domain repositories: **34**;
- infrastructure PostgreSQL adapters: **1**;
- central repositories: **0**;
- root repositories: **0**;
- root modules `velvet_bot/*.py`: **113**.

### Shared/private contracts

По `docs/shared_contract_inventory.*`:

- production Python files: **596**;
- functions inventoried: **3306**;
- registered private cross-module accesses: **136**;
- blocking known private contracts: **0**;
- exact duplicate groups: **55**;
- normalized near-duplicate groups: **92**;
- semantic near-duplicate groups: **9**.

Ноль blocking known contracts означает, что перечисленные обязательные private APIs мигрированы. Это не означает нулевой transitional debt: 136 accesses остаются зарегистрированным burn-down baseline для #419/#455/#457/#458/#459.

### Navigation

По `docs/generated/telegram_navigation_inventory.md`:

- scanned Python files: **604**;
- inline buttons: **1024**;
- reply buttons: **0**;
- navigation violations: **0**.

## Закрытые архитектурные долги

### PostgreSQL boundary

- external `Database._require_pool()` accesses: 0;
- applied migrations защищены от изменения;
- duplicate migration numbers блокируются;
- новый persistence-код допускается только в domain либо reviewed infrastructure boundary.

### P2 stability

- broad exception boundaries: 76;
- approved boundaries: 76;
- unresolved boundaries: 0;
- callback handlers: 98;
- late/missing acknowledgments: 0.

### Legacy Telegram layer

- active `velvet_bot.handlers` consumers: 0;
- physical legacy implementations: 0;
- aliases/facades: 0;
- root Router собирается четырьмя ordered bundles.

### Shared foundation

Public contracts введены для:

- safe edit и callback edit-or-answer;
- idempotent deletion;
- navigation/pagination primitives;
- text chunking;
- Telegram media download;
- typed retry/backoff;
- state/task mapping contracts;
- Supervisor и Ауф editing adapters.

Новые private cross-controller contracts не должны добавляться молча.

### Branch automation

PR #475 закрыл #461:

- feature branch mutation выполняется manual `workflow_dispatch`;
- обязательны exact target/source SHA;
- `main`/`master` запрещены;
- dry-run и full tests выполняются до обычного push;
- force-push, automatic merge и conflict resolution отсутствуют;
- giant runner-PR «не сливать» больше не является допустимым процессом.

## Текущая физическая структура

```text
velvet_bot/
  app/                         bootstrap и переходные runtime installers
  application/                 transport-neutral use cases
  core/                        config, access и базовые contracts
  domains/                     domain models, services и 34 repositories
  infrastructure/              PostgreSQL/provider/Telegram/filesystem adapters
  presentation/telegram/       root Router, 4 bundles, views и adapters
  services/                    integration/application services
  workers/                     WorkerManager и worker boundaries
  *.py                         113 root modules, 110 non-facade migration targets
```

## Главный P0: startup composition

`velvet_bot/app/__init__.py` остаётся переходным и выполняет:

- 2 installers до bootstrap;
- 25 installers внутри configured startup;
- всего **27 side-effect installation stages**.

Подтверждённые риски:

- package `__getattr__` запускает runtime side effects;
- worker implementation определяется порядком imports/assignments;
- несколько installers переписывают методы одних и тех же classes;
- `_INSTALLED` globals делают повторный startup process-state dependent;
- ошибка посередине может оставить partial patched state;
- новый hotfix вынужден угадывать фактический subclass после предыдущих installers.

Target: typed `ApplicationComposition`, factories/registries и explicit dependency assembly по #455.

## Главный P0: media delivery

Сейчас delivery затрагивает:

- `domains/media_generation/file_delivery_worker.py`;
- `domains/media_generation/friendly_worker.py`;
- GRS resilience/campaign/progress installers;
- image/video original delivery hotfixes;
- result recovery и active-worker fix layers.

PR #450/#456 обеспечивают важную production stabilization: готовый provider result можно восстановить и доставить без нового submit/attempt/charge. Они не являются target architecture.

Target #457:

- единая durable state machine от provider submit до notification;
- provider-neutral resolve/download/deliver/redeliver use cases;
- один Telegram adapter для image/video descriptors;
- recovery после restart из durable state;
- redelivery без provider submit и нового списания;
- удаление runtime `_deliver_best_effort` assignments и temporary hotfixes.

## P1 canonical boundaries

### Ауф portal/UI — #458

`app/*_install.py` всё ещё содержит presentation replacement, mapping и часть orchestration. Target — application use cases и canonical presentation adapters без SQL/controller replacement в `app`.

### Provider adapters — #459

Kie/GRS routing, model labels, retry и error normalization должны стать typed provider contracts. Live acceptance выполняется отдельно по #412.

### Package-wide drift gates — #460

Existing inventories видят важную часть debt, но постоянный CI gate должен дополнительно блокировать:

- новый unregistered foreign symbol/method assignment;
- новый SQL/database acquire в app/presentation;
- новые `*_install.py`, `*_hotfix.py`, `*_fix.py` без exception record;
- рост `type: ignore[method-assign]` и broad `Any`;
- возврат moved modules и private contracts;
- незарегистрированный рост monolithic modules.

### Root modules — #463

Из 113 root modules только 3 имеют justified public-facade contract. Остальные 110 мигрируются bounded families. Giant move PR запрещён: физический перенос не должен одновременно менять behavior.

## Ауф product/economy status

Слито:

- canonical wallet/runtime/photo/user portal;
- active Ауф protocol и persistent identifier migration;
- GRS/Kie queues, charging и reconciliation;
- retail price versions и fixed RUB packages;
- privacy-safe Telegram user registry;
- owner grant/user commands;
- system reference privacy;
- result recovery/redelivery stabilization.

Historical migrations, compatibility packages и dual-read `meow_*` FSM/transport values остаются до live retirement #438. Новые persistent `meow_*` identifiers запрещены.

## Эксплуатационные ворота

Архитектурный CI не заменяет внешнюю проверку. Остаются:

1. #407 — Linux VPS production cutover;
2. #409 — Supervisor Windows self-restart/update-and-restart;
3. #410 — post-deploy owner/workspace/AI/Ауф smoke;
4. #411 — отдельный staging bot/database;
5. #412 — live Kie/GRS routes, limits, credits и result contracts;
6. #408 — encrypted offsite backup и independent restore;
7. #438 — live compatibility retirement;
8. execution/provider/cost metrics.

## Правило следующих изменений

- новый Telegram controller не получает SQL;
- business operation сначала получает use case/domain service;
- новый installer/hotfix требует issue, owner и removal condition;
- foreign assignment требует зарегистрированный transitional contract;
- delivery behavior не расширяется новым patch layer без #457 plan;
- старый applied SQL не редактируется;
- feature branch mutation не создаёт runner-PR;
- live obligation не закрывается зелёным CI;
- canonical docs обновляются только по merged state и generated figures.
