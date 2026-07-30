# 2026-07-30 — Package-wide architecture drift gates

- Дата: 2026-07-30
- ID: `package-architecture-drift-gates`
- Issue: #460
- Линия/фаза: P1 architecture governance
- Статус: `завершено`
- Ветка: `feature/package-architecture-drift-gates`
- Базовый commit: `d18ad4fd24b3dfa84d255148aee065b97b52ea9b`

## Перед началом

### Цель

Расширить архитектурный контроль с root files и отдельных shared/private contracts на весь production package `velvet_bot`, зафиксировать фактический installer/monkeypatch graph и блокировать новый незарегистрированный debt внутри уже существующих packages.

### Исходный контекст

Root inventory фиксировал 113 модулей, Router inventory — 84 registrations, repository inventory — 35 persistence modules, shared-contract inventory — 136 private cross-module accesses. Эти gates не видели рост SQL и `Database.acquire()` в app/presentation, новые `*_install.py`/`*_hotfix.py`, foreign assignments, `_INSTALLED`, package `__getattr__`, `type: ignore[method-assign]`, `Any`, dynamic imports и монолитные функции внутри существующих файлов. `velvet_bot/app/__init__.py` уже выполнял 27 order-dependent installation stages, но measurable package-wide baseline отсутствовал.

### Планируемый объём

- AST scan всех production Python modules под `velvet_bot`;
- layer и target-package classification каждого модуля;
- LOC, functions/classes/handlers, branch proxy и maximum function length;
- internal/external imports и aiogram boundary checks;
- SQL/database acquire fingerprints вне persistence modules;
- dynamic imports и assignments в imported modules/classes/functions;
- installer-like files, install calls, `_INSTALLED` и package `__getattr__`;
- `Any`, `cast`, `type: ignore` и `method-assign` baseline;
- env reads, polling values и worker-registration observations;
- ordered startup installer graph с patched symbols;
- linkage с root/repository/router/shared/duplicate inventories;
- mandatory exemption registry с owner, reason, consumers, replacement, removal condition, regression test и issue;
- CI gate против новых и stale fingerprints.

### Критерии готовности

- inventory покрывает каждый текущий production module;
- startup graph содержит все 27 stages в порядке исполнения;
- каждый observed file/category fingerprint имеет ровно один complete exemption;
- новый или изменённый SQL/acquire/assignment/installer/typing fingerprint падает в CI;
- удалённый debt требует удаления stale exemption;
- root и shared-private fingerprints связаны с existing inventories;
- blocking known private contract count остаётся 0;
- #455/#457/#458/#459/#460/#463 получают measurable owner baseline;
- temporary baseline workflow отсутствует в итоговом tree;
- полный CI проходит.

### Риски и ограничения

Scanner использует статический AST и намеренно не пытается выполнить runtime import graph. Он фиксирует observable code contracts, но не доказывает фактическое поведение внешнего provider или Telegram. SQL detection может включать legitimate legacy/application code; поэтому current debt регистрируется exemption, а не автоматически переписывается giant PR. Fingerprint меняется при содержательном изменении наблюдаемого debt и требует review, но не должен зависеть от простого сдвига номера строки.

## После завершения

### Фактически сделано

- добавлен `scripts/inventory_package_architecture.py` для полного scan `velvet_bot`;
- зафиксированы 604 production modules и 128 870 LOC;
- каждый module имеет layer, intended target, size/complexity metrics, import/typing/runtime observations;
- linked baseline подтверждает 113 root modules, 84 Router imports, 35 repositories и 0 duplicate Router registrations;
- shared linkage подтверждает 596 files, 3306 functions, 136 private accesses, 0 blocking known contracts и duplicate groups 55/92/9;
- построен ordered graph из 27 startup installers с origin module и detected patched symbols;
- current debt агрегирован в 518 устойчивых file/category fingerprints вместо 1142 построчных исключений;
- categories включают SQL/acquire boundaries, aiogram/domain imports, dynamic imports, foreign assignments, installer files, `_INSTALLED`, package `__getattr__`, typing ignores/Any и monoliths;
- добавлен `docs/package_architecture_exemptions.json` с mandatory owner/reason/consumers/replacement/removal condition/regression/issue metadata;
- 518 exemptions распределены по burn-down owners #455/#457/#458/#459/#460/#463;
- generated machine JSON и human Markdown добавлены в version control;
- baseline создан exact-head fast-forward workflow run, который удалил собственный workflow в том же generated commit;
- добавлен `tests/test_package_architecture_inventory.py`, выполняющий полный `--check` и проверяющий coverage, metadata, fingerprints, installer order и отсутствие preview workflow.

### Миграции и совместимость

Миграций базы данных и runtime behavior нет. Scanner читает production source и existing generated inventories, но не импортирует `velvet_bot` application runtime. Existing debt не меняется и не объявляется исправленным: он становится registered baseline. Historical migrations не сканируются как новый production code. Root/shared inventories остаются отдельными canonical sources и связываются SHA-256 fingerprints вместо дублирования их логики.

### Проверки

Перед merge должны успешно пройти:

- `python scripts/inventory_package_architecture.py --check --label p1-package-architecture-baseline`;
- package architecture regression suite;
- полный unit test suite с PostgreSQL 16;
- bounded type check;
- Docker build и project notes contract;
- проверка отсутствия temporary preview workflow;
- PR mergeability и отсутствие unresolved review threads.

Preview run #4 успешно построил и fast-forward записал generated baseline из exact head `650687dec2555c8c8815b710ece099f50fa1d414`; generated commit `d9424361e860ea8b066f7390796a7a912c4a770a` удалил temporary workflow.

### PR и commit

- Issue: #460;
- PR: #478;
- ветка: `feature/package-architecture-drift-gates`;
- generated baseline commit: `d9424361e860ea8b066f7390796a7a912c4a770a`;
- итоговый squash merge commit фиксируется GitHub после зелёного CI.

### Незавершённое

Сам architecture debt не исправлен этим governance PR. Burn-down продолжается в #455 explicit composition, #457 unified delivery, #458 Ауф application/presentation, #459 provider adapters и #463 root-module migration. #460 закрывает возможность добавлять новый debt тихо и предоставляет измеримые counts для этих задач.

### Следующий шаг

После merge закрыть #460, обновить #213/#427 новым baseline и брать первый bounded P0 slice #455/#457. Любое изменение registered debt должно либо уменьшать соответствующий fingerprint/exemption, либо предоставлять новый issue-backed review, а не просто обновлять generated файлы ради зелёного CI.
