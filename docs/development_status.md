# Текущий статус разработки Velvet

Дата актуализации: 2 августа 2026 года.

Текущая стабильная версия: `1.3.0`.

Актуальный `main` на момент начала среза: `a564e0c05d0f8ddef82f8346d13cd14a5eaa0113`.

## Назначение

Velvet Archive — owner-oriented архивный Telegram-бот. Его домены: персонажи, истории, медиа, референсы, публикации, аналитика, AI-проверки, Ауф-генерации, кошелёк и эксплуатация владельцем.

Аукционный бот является отдельным продуктом. Ставки, лоты, колоды и режимы торгов в Velvet Archive не входят.

## Режим стабилизации

Приоритет определяется `docs/stabilization_policy.md`:

- стабилизировать и упрощать существующие сценарии;
- повышать надёжность, наблюдаемость и tenant isolation;
- новый код добавлять только как улучшение существующей функции;
- не объявлять production-ready то, что не прошло доступную живую проверку;
- applied migrations не редактировать.

## Что уже работает

- архив персонажей, историй, медиа и референсов;
- категории, вселенные, несколько историй и медиасеты;
- публичный архив, лайки, подписки и уведомления;
- preview и оригиналы изображений/видео;
- промты, Qwen/VL quality operations и визуальные дубли;
- аналитика канала и обсуждений;
- импорт истории Telegram;
- проверка, расписание и отправка публикаций;
- backup и автоматический restore drill;
- WorkerManager, Error Center и owner-only diagnostic bundles;
- Supervisor, Codex workflow и безопасная удалённая консоль;
- Ауф photo/video flows, очередь, списания, reconciliation и повторная доставка;
- розничные тарифы в вельветах, фиксированные рублёвые пакеты и реестр пользователей.

## Production foundation

Завершены в коде и CI:

- Python 3.13 и PostgreSQL 16;
- Dockerfile, Docker Compose и healthcheck;
- unit/integration tests, bounded type check и Docker CI;
- автоматический backup restore drill;
- release/tag workflows;
- project notes contract;
- безопасный manual branch-maintenance workflow;
- package-wide architecture drift gate;
- стабильный релиз `1.3.0`.

Windows-, staging-, provider- и offsite-проверки перечислены отдельно. Наличие кода и зелёного CI не закрывает внешнюю эксплуатационную проверку.

## Последние слитые функциональные изменения

### Ауф и экономика

- canonical wallet/runtime/photo/user portal поставлены серией PR #403/#404/#405/#443;
- active Telegram protocol переведён с Мяу на Ауф PR #428;
- persistent PostgreSQL/module identifiers мигрированы PR #446;
- recovery готового provider result без новой генерации добавлена PR #450/#456;
- PR #473 отделил API-себестоимость от розничной цены, добавил фиксированные пакеты, команды `/velvet_grant`, `/velvet_user`, `/velvet_users`, privacy-safe user registry и системную изоляцию референсов;
- старые операции и завершённые задачи не пересчитываются новыми тарифами.

### Shared contracts, docs и branch maintenance

- PR #462 создал package-wide shared-helper inventory и публичные Telegram contracts;
- PR #468/#469 мигрировали Supervisor и Ауф editing families с private cross-module helpers;
- PR #475 добавил SHA-guarded `workflow_dispatch` для deterministic maintenance непротектированных веток без giant runner-PR, force-push и automatic conflict resolution;
- PR #476 синхронизировал canonical status, project memory, architecture audit и changelog с generated inventories.

### Важная граница совместимости

Активный пользовательский и module protocol называется Ауф. Historical migrations, compatibility packages и dual-read FSM/transport aliases с `meow_*` пока существуют до live retirement #438. Их наличие не означает возврат старого бренда и не позволяет добавлять новые `meow_*` identifiers.

## Архитектурный статус

### Закрытые линии

- private PostgreSQL pool access: **0 production accesses**;
- unresolved P2 broad/callback debt: **0**;
- legacy handler files/implementations/aliases: **0**;
- root Router direct imports `velvet_bot.handlers.*`: **0**;
- duplicate registrations между четырьмя Router bundles: **0**;
- central/root repositories: **0**;
- blocking known private helper contracts: **0**;
- незарегистрированный package-wide architecture debt: **0** — каждый observed fingerprint обязан иметь reviewed exemption.

### Воспроизводимые текущие числа

По generated inventories текущего среза:

- production modules package-wide: **638**;
- production LOC: **139 035**;
- root modules `velvet_bot/*.py`: **113**;
- активные Router imports в четырёх bundles: **84**;
- runtime compatibility components: **8**;
- repository modules: **44**;
- domain repositories: **37**;
- infrastructure PostgreSQL adapters: **7**;
- startup installer stages: **28**;
- registered package architecture fingerprints: **546**;
- mandatory package exemptions: **546**;
- production Python files в shared-contract inventory: **631**;
- функций inventoried: **3597**;
- registered private cross-module debt: **182**;
- exact / normalized / semantic duplicate groups: **62 / 97 / 9**;
- Telegram navigation scan: **631 Python files**, **1049 inline buttons**, **0 violations**.

546 package fingerprints — это измеренный текущий debt, а не 518 исправленных проблем. Новый или изменённый fingerprint блокирует CI до явного owner/reason/replacement/removal issue review; удалённый debt требует удаления stale exemption.

Источники: `docs/package_architecture_inventory.*`, `docs/package_architecture_exemptions.json`, `docs/architecture_layout_inventory.*`, `docs/repository_layout_inventory.*`, `docs/shared_contract_inventory.*`, `docs/generated/telegram_navigation_inventory.md`.

### Текущий installer graph

`velvet_bot/app/__init__.py` по-прежнему является переходной границей:

- 2 side-effect installers выполняются до bootstrap;
- 25 installers выполняются внутри configured startup;
- итоговый worker/UI behavior зависит от порядка runtime assignments;
- package `__getattr__` всё ещё запускает composition side effects.

Package inventory фиксирует для каждого stage origin module и detected patched symbols. Это не target architecture. Исправление ведётся в #455, а единый media delivery pipeline — в #457.

## P3 и текущий кодовый долг

### P3A–P3E

Завершены:

- источники истины и generated inventories введены;
- root Router собирается четырьмя ordered bundles;
- активные Telegram controllers перенесены в canonical presentation paths;
- старые handler aliases удалены;
- repository layout ограничен domain/infrastructure boundaries;
- package-wide drift gate #460 введён и связывает root/router/repository/shared baselines.

### P3F typing

Первый bounded mypy gate действует и проходит в CI. Расширение scope выполняется постепенно; включение strict mode на весь repository одним PR запрещено. Package inventory отдельно fingerprinted текущие `Any`, `type: ignore` и `method-assign` usages, чтобы их рост не проходил тихо.

### Приоритет P0/P1

1. #455 — explicit composition root вместо 27-stage side-effect startup graph.
2. #457 — единый durable provider-neutral media delivery/redelivery pipeline.
3. #458 — перенос Ауф portal/UI из `app/*_install.py` в application/presentation.
4. #459 — canonical provider adapters, routing и retry contracts.
5. #463 — bounded migration 110 non-facade root modules.
6. #419 — дальнейшее сжигание зарегистрированного shared/private helper debt.

PR #450/#456 считаются временной stabilization, а не целевой delivery architecture. #460 закрывает измерение и CI-контроль, но не подменяет burn-down перечисленных задач.

## Hermes Brain: готовность к rollout

В feature branch реализованы:

- Obsidian-compatible Vault с entity registry, access matrix и политиками
  context window, compression, cache, short/long memory и handoff;
- deterministic compiler, SHA-256 manifest и installed-context verifier;
- отдельные Hermes/Codex packs для Каэля, Velvet Coder и Макса;
- compiled deny-all profile Velvet Librarian;
- Codex global AGENTS, scoped skills и strict JSON output schema;
- structured task handoff, legacy-compatible summary и memory candidates в
  orchestration ledger;
- fixed runtime config для cwd, compression и autonomous loop circuit breaker;
- preflight/live smoke контракты, которые ловят перепутанный entity/project или
  изменённый context file.

Не завершено живой средой: server reconcile/restart и post-rollout smoke. До
этого capability имеет статус «готово в коде», а не «установлено в production».

## Эксплуатационные обязательства

Не закрыты одним CI:

1. #407 — production cutover на Linux VPS.
2. #409 — Supervisor self-restart/update-and-restart на целевой Windows.
3. #410 — единый post-deploy owner/workspace/AI/Ауф smoke.
4. #411 — staging bot/database и безопасные credentials.
5. #412 — live Kie/GRS routes, limits, credits, payload/result contracts.
6. #408 — encrypted offsite backup и независимый restore drill.
7. #438 — live retirement dual-read `meow_*` compatibility.
8. AI duration/error/provider/model/cost-unit metrics.
9. Hermes Brain reconcile и live проверка context manifests всех сущностей.

## Документация и контроль

- `docs/project_memory.md` — долгосрочная карта;
- `docs/development_status.md` — текущий статус;
- `docs/architecture_target.md` — целевая структура;
- `docs/ARCHITECTURE_AUDIT.md` — текущий аудит;
- `docs/stabilization_policy.md` — ворота стабилизации;
- `docs/package_architecture_inventory.*` — полный module/installer/violation baseline;
- `docs/package_architecture_exemptions.json` — mandatory owners и retirement conditions;
- `docs/*_inventory.*` — остальные воспроизводимые измерения;
- `docs/runbooks/branch_maintenance.md` — безопасная mutation feature-веток;
- `docs/worklog/` — проверяемая история работ;
- `CHANGELOG.md` — только слитые заметные изменения.

CI блокирует содержательный PR без завершённого worklog и блокирует новый/stale architecture fingerprint без reviewed exemption.

## Правила дальнейшей разработки

- Telegram controller не получает новый SQL;
- business operation создаётся через use case/domain service;
- новый installer/hotfix не добавляется без issue, owner и removal condition;
- private cross-module access не становится новым публичным contract молча;
- изменение registered package debt обновляет fingerprint только вместе с содержательным worklog и issue-backed review;
- feature branch maintenance использует PR либо SHA-guarded workflow, но не runner-PR «не сливать»;
- старые applied migrations не редактируются;
- infrastructure capability не называется production-ready без доступной live-проверки;
- каждая работа фиксирует checks, PR/commit, остаток и следующий шаг.

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

<!-- pr-663-byesu-image-quality-architecture-slice -->
## Срез Byesu GPT Image quality PR #663 от 7 августа 2026 года

Текущий воспроизводимый архитектурный срез после синхронизации с retirement #457:

- package production modules: **656**;
- inventoried functions: **3830**;
- registered transitional private accesses: **180**;
- blocking known contracts: **0**;
- #457 уже объединён в `main`; live provider и Telegram acceptance для нового GPT Image маршрута остаются отдельными эксплуатационными проверками.
<!-- /pr-663-byesu-image-quality-architecture-slice -->

<!-- codex-recovery-notification-architecture-slice -->
## Срез Codex recovery notification от 8 августа 2026 года

Воспроизводимый repository baseline после добавления persistent-deduplicated recovery notification:

- package production modules: **661**;
- package production LOC: **145308**;
- Codex availability/routing authority и пятичасовой probe cadence не менялись;
- Telegram transport использует существующий main Velvet bot/application path;
- production rollout и live canary остаются отдельной эксплуатационной проверкой.
<!-- /codex-recovery-notification-architecture-slice -->
