# Сессия: runtime evidence wiring для issue #584

- Дата: 2026-08-05
- ID: `584evidence641a0c9dd1161de8a061e6a`
- Линия/фаза: Hermes Brain stabilization, repository-only runtime wiring
- Статус: частично
- Issue: #584
- Ветка: `feat/584-runtime-evidence-wiring-v2`
- Базовый commit: `6c0174738f60c13b579f4dc9c78389cbf07ea3ae`
- Контракт: `task_type=code`, `complexity=complex`, `risk=high`,
  `mutation_policy=isolated_pr_only`, `requested_tier=high_risk`

## Перед началом

### Цель

Связать readiness/evidence contract из PR #640 с canonical launcher-backed
runtime без изменения существующего tier routing и Git mutation audit. Runner
должен публиковать effective cwd, final branch и execution evidence отдельно от
mutation, а central router должен возвращать полный changed-file evidence PR.

### Исходный контекст

PR #640 слит в базовый commit и добавил manifest-backed policy, `coderctl` и
fail-closed review gate. Canonical process boundary уже реализован PR #629:
runner делегирует Codex root-owned launcher через Unix socket и disposable
Docker container. Production rollout #594 не выполнялся и не входит в эту
сессию.

### Планируемый объём

- добавить узкий subclass launcher manager для runtime evidence;
- сохранить `codex_tier_runner.py` единственным источником mutation audit;
- добавить evidence-aware subclass active tier router;
- получить полный paginated список PR files с count-consistency gate;
- обновить exact-release mounts, import graph, systemd readability и image entrypoint;
- добавить focused behavioral/static regression coverage;
- не выполнять server operations, deploy, restart или canary.

### Критерии готовности

- actual tool/file event устанавливает `execution_started=true`;
- lifecycle-only output не считается execution;
- adapter не записывает `mutation_started`;
- mutation остаётся OR Git/base/push/PR evidence существующего tier audit;
- Velvet и Max используют один context launcher entrypoint;
- active router сохраняет typed tier contract и effective runner cwd;
- PR file evidence полное, сортированное, paginated и fail-closed при drift;
- focused tests, required CI и exact-head review завершаются без blockers.

### Риски и ограничения

Изменение затрагивает control plane, но не добавляет privileges. Нельзя
создавать второй execution lifecycle, расширять GitHub path из caller payload,
выдавать Docker socket/systemd/model-facing secrets или считать execution
мутацией. Local compatibility backend остаётся только explicit rollback gate.
Server-side acceptance и rollout остаются незавершёнными.

## После завершения

### Фактически сделано

- добавлен `ContextLauncherTierProviderManager`, наследующий canonical launcher
  manager и дописывающий `process_cwd`, `final_branch`, `execution_started` и
  начальный `push_or_pr_observed=false`;
- execution выводится из actual tool/file events либо trusted launcher state;
- mutation logic не продублирована: adapter вызывает существующий tier `_success`;
- добавлен `EvidenceTierAwareCoderRouter`, наследующий typed tier router;
- GitHub PR files читаются страницами по 100, сортируются и сверяются с
  `changed_files`; drift и превышение 3000 файлов блокируют evidence snapshot;
- canonical coder Compose, operator image/orchestration, runtime source guard и
  systemd readability contract переключены на новые exact-release sources;
- добавлен focused suite `test_hermes_issue_584_runtime_contract.py`.

### Миграции и совместимость

Миграций БД и ledger schema migration нет: новые поля additive. Existing
`codex_tier_runner.py`, provider chain, launcher client и fixed-schema host
launcher не заменяются. Operator HTTP routes и typed submit schema сохраняются.
Canonical Compose не включает local rollback backend. Production state не
изменялся.

### Проверки

- exact-head GitHub type check: PASS;
- project notes contract initial run: FAIL из-за отсутствия обязательного
  worklog template; исправляется этим commit;
- focused runtime tests, full unit shards, Docker/security и branch-protection
  checks ожидают повторный exact-head CI;
- repository diff review: no Docker socket, arbitrary GitHub path, secret
  projection, deploy trigger или production action added.

### PR и commit

- PR: #641 `Hermes: wire launcher runtime evidence for #584`;
- initial implementation: `0ac9dd1161de8a061e6a4c51e43adb0dbe4f04a4`;
- worklog correction commit будет зафиксирован GitHub contents API;
- final exact head и merge commit будут внесены в PR body после terminal CI.

### Незавершённое

- terminal exact-head CI после worklog correction;
- independent exact-diff review и merge;
- server-side runtime acceptance, direct/delegated dry-runs и production context
  install не выполняются без отдельного server phase;
- issue #584 остаётся открытым после repository merge.

### Следующий шаг

Дождаться нового exact-head CI, исправить только фактические blockers в PR #641,
обновить PR body доказательствами, снять draft и merge с expected head SHA. После
merge продолжить repository-only backlog без deploy или restart.
