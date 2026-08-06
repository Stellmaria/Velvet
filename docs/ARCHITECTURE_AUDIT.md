# Актуальный аудит архитектуры Velvet

Дата актуализации: 2 августа 2026 года.

Проверенный baseline `main` перед срезом: `d18ad4fd24b3dfa84d255148aee065b97b52ea9b`.

## Объём проверки

Проверены:

- все 638 production Python modules под `velvet_bot`;
- application bootstrap и startup composition;
- Router bundles и порядок Telegram controllers;
- domain/application/infrastructure boundaries;
- PostgreSQL repositories и migrations;
- Ауф wallet, provider routing, charging, queue и delivery;
- shared/private cross-module contracts;
- runtime installers, foreign assignments и compatibility components;
- SQL/database acquire, dynamic imports и typing debt;
- module size, maximum function length, handlers, env/polling и worker observations;
- generated package, architecture, repository, navigation и stability inventories;
- Supervisor, branch maintenance, backup и CI contracts;
- canonical status documents и открытые operational gates.

## Итог

Velvet имеет рабочие логические domain/application/persistence boundaries, закрытый private-pool debt, централизованный Telegram root Router и нулевой active legacy-handler layer. Package-wide inventory теперь блокирует новый незарегистрированный debt внутри существующих packages, где один root-count раньше бодро сообщал, что всё прекрасно, пока monkeypatch-граф разрастался этажом ниже.

Целевая архитектура при этом ещё не достигнута. Главный correctness-risk остаётся в `velvet_bot/app` и media generation layers: startup собирается цепочкой side-effect installers, итоговые workers/controllers зависят от runtime assignments, а delivery распределена между canonical classes и временными hotfix/recovery layers.

Hermes Brain добавлен как отдельный deployment/control-plane слой и не меняет
domain/application/persistence boundaries `velvet_bot`. Его собственные границы:
versioned per-entity context packs, SHA-256 verification, отдельные
CODEX_HOME/workspaces, schema-bound handoff/output и deny-all Librarian. Code/CI
готовность не закрывает server reconcile и live smoke.

## Воспроизводимый baseline

### Package-wide scan

По `docs/package_architecture_inventory.*` и `docs/package_architecture_exemptions.json`:

- production modules: **638**;
- production LOC: **139 035**;
- layer counts: application 21, composition 63, core 7, domain 179, infrastructure 27, other 1, presentation 215, root 114, service 8, worker 3;
- startup installer stages: **28**;
- registered file/category fingerprints: **546**;
- mandatory exemptions: **546**;
- unregistered fingerprints: **0**;
- stale exemptions: **0**.

Текущие fingerprint categories:

- SQL outside persistence: **107**;
- `Database.acquire()` outside persistence: **88**;
- `Any` usage: **106**;
- foreign assignments: **37**;
- `_INSTALLED` sentinels: **39**;
- installer/hotfix/fix modules: **22**;
- package `__getattr__`: **20**;
- domain aiogram imports: **19**;
- dynamic imports: **17**;
- `type: ignore`: **15**, из них `method-assign`: **7**;
- monolithic modules: **16**;
- monolithic functions: **24**;
- domain import из app/presentation: **1**.

Это registered debt, не список автоматически исправленных дефектов. Fingerprint агрегируется по `file + category + содержимое наблюдаемого debt`, поэтому простой сдвиг строк не создаёт шум, а новый SQL/assignment/typing escape меняет ID и требует review.

Exemptions распределены между owner issues #455/#457/#458/#459/#460/#463 и обязаны содержать owner, reason, consumers, replacement, removal condition, regression test и issue reference.

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

- repository modules: **44**;
- domain repositories: **37**;
- infrastructure PostgreSQL adapters: **7**;
- central repositories: **0**;
- root repositories: **0**;
- root modules `velvet_bot/*.py`: **113**.

### Shared/private contracts

По `docs/shared_contract_inventory.*`:

- production Python files: **631**;
- functions inventoried: **3597**;
- registered private cross-module accesses: **182**;
- blocking known private contracts: **0**;
- exact duplicate groups: **62**;
- normalized near-duplicate groups: **97**;
- semantic near-duplicate groups: **9**.

Package gate связывает shared/private и root-module SHA-256 fingerprints. Ноль blocking known contracts означает, что перечисленные обязательные private APIs мигрированы. Это не означает нулевой transitional debt: 182 accesses остаются зарегистрированным burn-down baseline для #419/#455/#457/#458/#459.

### Navigation

По `docs/generated/telegram_navigation_inventory.md`:

- scanned Python files: **631**;
- inline buttons: **1049**;
- reply buttons: **0**;
- navigation violations: **0**.

## Закрытые архитектурные долги

### PostgreSQL boundary

- external `Database._require_pool()` accesses: 0;
- applied migrations защищены от изменения;
- duplicate migration numbers блокируются;
- новый persistence-код допускается только в domain либо reviewed infrastructure boundary.

### P2 stability

- broad exception boundaries: 103;
- approved boundaries: 103;
- unresolved boundaries: 0;
- callback handlers: 132;
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

### Package-wide drift gate

PR #478 закрывает #460:

- scanner читает весь `velvet_bot`, не импортируя application runtime;
- machine inventory и human Markdown генерируются одной командой;
- current violations и exemptions обязаны совпадать один к одному;
- новый fingerprint падает как unregistered violation;
- удалённый debt падает как stale exemption;
- root/shared fingerprint drift требует отдельной классификации;
- blocking known private contract count обязан оставаться 0;
- temporary baseline workflow удалён из итогового tree;
- unit-test CI выполняет полный `--check` на каждом PR.

## Текущая физическая структура

```text
velvet_bot/
  app/                         bootstrap и 63 composition modules/installers
  application/                 21 transport-neutral use-case modules
  core/                        7 config/access/base contract modules
  domains/                     179 domain modules и 37 repositories
  infrastructure/              27 PostgreSQL/provider/Telegram/filesystem adapters
  presentation/                215 Telegram presentation modules
  services/                    8 integration/application service modules
  workers/                     3 worker boundary modules
  *.py                         113 classified root modules + package __init__
```

## Главный P0: startup composition

`velvet_bot/app/__init__.py` остаётся переходным и выполняет:

- 2 installers до bootstrap;
- 25 installers внутри configured startup;
- всего **28 side-effect installation stages**.

Package inventory теперь фиксирует exact order, origin module и detected patched symbols каждого stage. Первый stage — `install_runtime_stability`, последний — `install_auf_branding`.

Подтверждённые риски:

- package `__getattr__` запускает runtime side effects;
- worker implementation определяется порядком imports/assignments;
- несколько installers переписывают методы одних и тех же classes;
- `_INSTALLED` globals делают повторный startup process-state dependent;
- ошибка посередине может оставить partial patched state;
- новый hotfix вынужден угадывать фактический subclass после предыдущих installers.

Target: typed `ApplicationComposition`, factories/registries и explicit dependency assembly по #455. Package exemptions с owner `application-composition` должны уменьшаться по мере migration, а не просто менять fingerprints.

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

Media-delivery exemptions в package registry дают measurable burn-down и должны удаляться вместе с retiring patches.

## P1 canonical boundaries

### Ауф portal/UI — #458

`app/*_install.py` всё ещё содержит presentation replacement, mapping и часть orchestration. Target — application use cases и canonical presentation adapters без SQL/controller replacement в `app`.

### Provider adapters — #459

Kie/GRS routing, model labels, retry и error normalization должны стать typed provider contracts. Live acceptance выполняется отдельно по #412.

### Package-wide drift gates — #460

Статус: governance gate завершён. Он не исправляет существующие 546 fingerprints, но делает их measurable, owned и non-silent. Обновление generated baseline без содержательного worklog и issue-backed change не считается исправлением.

### Root modules — #463

Из 113 root modules только 3 имеют justified public-facade contract. Остальные 110 мигрируются bounded families. Giant move PR запрещён: физический перенос не должен одновременно менять behavior. Root fingerprint связан с package gate и не может измениться без классификации.

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
- новый/изменённый package fingerprint требует reviewed exemption либо удаления debt;
- stale exemption удаляется вместе с debt, а не хранится как памятник;
- delivery behavior не расширяется новым patch layer без #457 plan;
- старый applied SQL не редактируется;
- feature branch mutation не создаёт runner-PR;
- live obligation не закрывается зелёным CI;
- canonical docs обновляются только по merged state и generated figures.

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

<!-- arthur-librarian-phase2-architecture-slice -->
## Срез Arthur Librarian Phase 2 от 6 августа 2026 года

Дата среза: `2026-08-05`.

Контракт стабильного релиза: `v1.3.0`.

Воспроизводимый package/shared-contract baseline после выделения отдельного runtime Arthur:

- package production modules: **659**;
- inventoried functions: **3748**;
- registered transitional private accesses: **170**;
- blocking known private contracts: **0**;
- целевая консолидация временных delivery/composition слоёв остаётся в **#457** и **#455**.

Этот срез подтверждает code/CI scope Phase 2 и не означает production rollout или закрытие live obligations #409/#410/#412/#438. Compatibility identifiers `meow_*` остаются временными до отдельного retirement.
<!-- /arthur-librarian-phase2-architecture-slice -->

<!-- issue-605-error-center-batching-architecture-slice -->
## Срез Error Incident Center batching от 6 августа 2026 года

Дата среза: `2026-08-05`.

Контракт стабильного релиза: `v1.3.0`.

Воспроизводимый package/shared-contract baseline implementation-среза #605:

- package production modules: **659**;
- package production LOC: **145345**;
- inventoried functions: **3860**;
- registered transitional private accesses: **184**;
- blocking known contracts: **0**;
- exact / normalized / semantic duplicate groups: **68 / 98 / 9**;
- registered package architecture fingerprints: **537**;
- целевая консолидация media delivery и переходных persistence/composition boundaries остаётся в **#457** и **#455**.

Этот срез подтверждает только code/CI scope #605. Production storm acceptance, `pg_stat_statements`, WAL/IO, latency и Telegram rate требуют live-доступа и не закрываются зелёным CI. Обязательства #409/#410/#412/#438 и временные `meow_*` compatibility layers остаются открытыми.
<!-- /issue-605-error-center-batching-architecture-slice -->

<!-- issue-457-legacy-delivery-retirement -->
## Retirement legacy media delivery installers — 6 августа 2026 года

Durable media delivery PR #488 остаётся единственным production ownership path. Четыре neutralized installer слоя удалены из startup composition; runtime method replacement `install_delivery_handler` удалён; active Friendly worker сохраняет явный no-op для inherited legacy delivery phase.

Воспроизводимый baseline current feature head:

- package production modules: **655**;
- inventoried functions: **3830**;
- registered transitional private accesses: **180**;
- blocking known contracts: **0**;
- startup installer stages: **21**;
- registered package architecture fingerprints: **521**.

Repository implementation #457 завершена этим срезом, но live provider/Telegram acceptance остаётся #410/#412. Зелёный CI не подтверждает production restart, CDN/expired URL или no-double-charge matrix.
<!-- /issue-457-legacy-delivery-retirement -->
