# 2026-07-30 — Синхронизация canonical docs с current main

- Дата: 2026-07-30
- ID: `canonical-docs-sync-2026-07-30`
- Issue: #425
- Линия/фаза: P3A sources of truth
- Статус: `завершено`
- Ветка: `docs/sync-current-main-2026-07-30`
- Базовый commit: `9a32e5f1118c89bff3c91f0d517c38bd8bad24e7`

## Перед началом

### Цель

Привести `development_status`, `project_memory`, architecture audit и changelog к фактическому состоянию `main` после Ауф, shared-helper, architecture и branch-maintenance PR, не закрывая live obligations одним зелёным CI.

### Исходный контекст

Canonical docs были датированы 21 июля и содержали устаревшие figures: 60 active routers, 30/33 domain repositories, незавершённый shared-helper inventory и формулировку о практически завершённой физической архитектуре. С 21 по 30 июля были слиты active Ауф protocol/identifier migrations, result recovery, shared package, editing family migrations, retail/user registry и safe branch maintenance. Installer/delivery debt при этом вырос и был вынесен в #455/#457/#458/#459/#460/#463.

### Планируемый объём

- обновить дату и sync baseline `main`;
- получить counts только из generated inventories;
- описать shipped Ауф/economy/user registry changes;
- отделить временную result recovery от target delivery architecture;
- зафиксировать 27-stage installer graph и package-private debt;
- сохранить live Windows/staging/provider/backup obligations открытыми;
- не объявлять historical `meow_*` compatibility полностью удалённой;
- сократить changelog до merged current story и release history;
- добавить regression contract против повторного расхождения документов.

### Критерии готовности

- status, memory и audit датированы 30 июля 2026;
- одинаковые generated counts присутствуют во всех canonical docs;
- changelog содержит только слитые изменения и release `1.3.0`;
- #455/#457 и PR #450/#456 классифицированы как target debt/temporary stabilization;
- #409/#410/#412/#438 остаются live obligations;
- branch maintenance #461 отражена как завершённая;
- старые figures 60 routers и 30 repositories не возвращаются;
- full CI проходит.

### Риски и ограничения

Документы фиксируют baseline конкретного `main`, а не вечную истину. Следующие code PR могут изменить generated counts; regression должен вынуждать обновлять docs вместе с inventory, но не должен требовать переписывать historical worklogs. Changelog можно сокращать по merged themes, однако applied migrations и release heading изменять нельзя.

## После завершения

### Фактически сделано

- `docs/development_status.md` переписан как текущий operational/architecture status;
- `docs/project_memory.md` обновлён с сохранением обязательных линий A–E и historical heading;
- `docs/ARCHITECTURE_AUDIT.md` теперь различает закрытые boundaries, transitional installer graph и target P0/P1;
- `CHANGELOG.md` сокращён до current merged Unreleased и release `1.3.0`, подробная археология оставлена в worklogs;
- зафиксированы 84 Router imports, 113 root modules, 35 repositories, 8 runtime compatibility components;
- зафиксированы 596 production files, 3306 functions, 136 registered private accesses и 0 blocking known contracts;
- зафиксирован navigation baseline 604/1024/0;
- отражены retail tariffs, fixed packages, user registry и system-reference privacy PR #473;
- отражён SHA-guarded branch maintenance PR #475;
- PR #450/#456 названы temporary delivery stabilization до #457;
- historical/dual-read `meow_*` compatibility оставлена до #438;
- добавлен `tests/test_canonical_docs_sync.py`, читающий generated JSON/Markdown inventories и блокирующий stale figures/false closure.

### Миграции и совместимость

Миграций базы данных и runtime behavior нет. Stable version остаётся `1.3.0`, release heading `## [1.3.0] - 2026-07-17` сохранён. Historical worklogs не переписывались. Active Ауф protocol не меняется, `meow_*` упоминается только как historical/dual-read compatibility.

### Проверки

Перед merge должны пройти:

- canonical docs regression;
- полный unit test suite;
- bounded type check;
- project notes contract;
- Docker/backup workflows, если path filters запустят их;
- проверка PR mergeability и отсутствия unresolved review threads.

### PR и commit

- Issue: #425;
- ветка: `docs/sync-current-main-2026-07-30`;
- PR и итоговый squash commit фиксируются GitHub после публикации и merge.

### Незавершённое

Live acceptance #407–#412/#438 и code debt #455/#457/#458/#459/#460/#463 остаются открытыми. Синхронизация docs не подменяет их выполнение. Umbrella #213 и index #427 должны получить ссылку на новый merged baseline после merge PR.

### Следующий шаг

После зелёного CI слить PR и закрыть #425, затем обновить #213/#427 итоговым commit и продолжить первую reviewable P0/P1 migration, не создавая ещё один installer/hotfix layer.
