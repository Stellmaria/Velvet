# Текущий статус разработки Velvet

Дата актуализации: 30 июля 2026 года.

Текущая стабильная версия: `1.3.0`.

Актуальный `main` на момент начала среза: `d18ad4fd24b3dfa84d255148aee065b97b52ea9b`.

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

- production modules package-wide: **604**;
- production LOC: **128 870**;
- root modules `velvet_bot/*.py`: **113**;
- активные Router imports в четырёх bundles: **84**;
- runtime compatibility components: **8**;
- repository modules: **35**;
- domain repositories: **34**;
- infrastructure PostgreSQL adapters: **1**;
- startup installer stages: **27**;
- registered package architecture fingerprints: **518**;
- mandatory package exemptions: **518**;
- production Python files в shared-contract inventory: **596**;
- функций inventoried: **3306**;
- registered private cross-module debt: **136**;
- exact / normalized / semantic duplicate groups: **55 / 92 / 9**;
- Telegram navigation scan: **604 Python files**, **1024 inline buttons**, **0 violations**.

518 package fingerprints — это измеренный текущий debt, а не 518 исправленных проблем. Новый или изменённый fingerprint блокирует CI до явного owner/reason/replacement/removal issue review; удалённый debt требует удаления stale exemption.

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

<!-- media-delivery-shared-baseline:start -->
## Актуальный shared-contract baseline после #511

- Production Python files: 629.
- Functions: 3597.
- Registered transitional private accesses: 182.
- Blocking known contracts: 0.
- Exact duplicate groups: 60.
- Normalized duplicate groups: 97.
- Semantic near-duplicate groups: 9.
- Durable media delivery boundary: #457 и #511.
<!-- media-delivery-shared-baseline:end -->
