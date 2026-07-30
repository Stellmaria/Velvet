# 2026-07-30 — Безопасное обслуживание feature-веток

- Дата: 2026-07-30
- ID: `safe-branch-maintenance`
- Issue: #461
- Линия/фаза: P2 branch automation hardening
- Статус: `завершено`
- Ветка: `fix/safe-branch-maintenance`
- Базовый commit: `a14baa7ecc34be04f2ce067b3f2d0a634fec35b9`

## Перед началом

### Цель

Заменить giant runner-PR и временные feature-specific write workflows одним ручным, generic и auditable механизмом обслуживания непротектированных веток.

### Исходный контекст

Исторические PR #444 и #454 содержали десятки unrelated commits ради mutation другой ветки и были закрыты без merge. В PR #462 временно появлялся self-mutating workflow с hard-coded branch, автоматическим merge `main`, разрешением конфликтов и `contents: write`. После удаления временного workflow в `main` отсутствовал безопасный reusable replacement, поэтому branch maintenance снова выполнялась ручными API-операциями без единого audit trail.

### Планируемый объём

- добавить один ручной workflow для детерминированного cherry-pick;
- ограничить target allowlist непротектированными feature-ветками;
- требовать точные expected target SHA и source commit SHA;
- выполнять dry-run, diff plan и полный unit test suite до записи;
- запретить force-push, automatic merge и conflict resolution;
- обеспечить concurrency lock и повторную SHA-проверку перед push;
- задокументировать runbook и добавить regression guard.

### Критерии готовности

- workflow не может изменить `main` или `master`;
- stale target SHA останавливает запуск до mutation;
- source ограничен одним single-parent commit;
- changed files, diff stat, tests и resulting commit видны в одном run summary;
- повторный запуск является no-op и не создаёт duplicate commit;
- `contents: write` workflows перечислены в явном CI allowlist;
- временный `apply-shared-helper-migration.yml` отсутствует;
- полный repository CI проходит.

### Риски и ограничения

Workflow намеренно не выполняет rebase, merge диапазона commits или автоматическое разрешение конфликтов. Он не доказывает качество source change сам по себе: source должен быть reviewable commit, а полный test suite лишь блокирует очевидную несовместимость. Защищённые ветки обслуживаются отдельным PR/release flow.

## После завершения

### Фактически сделано

- добавлен `.github/workflows/branch-maintenance.yml` с единственным allowlisted action `cherry-pick`;
- target ограничен префиксами `agent/`, `feature/`, `fix/`, `chore/` и `maintenance/`;
- обязательны два полных immutable SHA;
- target SHA проверяется до dry-run и повторно непосредственно перед push;
- merge commits отклоняются, conflicts не разрешаются автоматически;
- dry-run выполняется через `git cherry-pick --no-commit` и `git diff --check`;
- полный unit test suite запускается с PostgreSQL 16 до создания commit;
- push выполняется обычным fast-forward push без force;
- ancestor/equivalent-patch retries завершаются auditable no-op;
- workflow summary и семидневный artifact содержат план, tests и результат;
- добавлен runbook с разделением normal PR и maintenance use cases;
- добавлен regression test против branch-specific write workflows и небезопасных Git-команд.

### Миграции и совместимость

Миграций базы данных и runtime-кода нет. Existing release workflows `release.yml` и `tag-stable-release.yml` сохранены в allowlist, поскольку их `contents: write` ограничен созданием GitHub release и annotated stable tag. Новый workflow не запускается автоматически и не меняет поведение приложения.

### Проверки

В PR должны пройти полный unit test suite, type check, Docker build и project notes contract. Отдельный regression проверяет immutable SHA contract, allowlist веток, dry-run, idempotency, отсутствие force-push и inventory всех `contents: write` workflows.

### PR и commit

- Issue: #461;
- ветка: `fix/safe-branch-maintenance`;
- PR и итоговый squash commit фиксируются GitHub после публикации и merge.

### Незавершённое

Обязательных code changes по #461 не остаётся. Live workflow dispatch возможен только после merge файла workflow в default branch; первый реальный maintenance run должен использовать малую тестовую feature-ветку и сохранить resulting run ID как operational evidence.

### Следующий шаг

После зелёного CI слить PR, закрыть #461 и использовать этот workflow вместо runner-PR или temporary branch-specific Actions. P0 delivery/composition issues #455/#457 продолжаются отдельными behavioral slices и не должны использовать automation как способ скрыть giant diff.
