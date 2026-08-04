# Сессия: brain/context readiness и evidence contracts #584

- Дата: 2026-08-04
- ID: `2940c8c287a242d7818c9f3eba98a642`
- Линия/фаза: hotfix/эксплуатация вне фаз, Hermes Brain stabilization
- Статус: частично
- Issue: #584
- Ветка: `issue/584-brain-context-readiness`
- Базовый commit: `e6a77aa7fcb7cdab11581f1503d40230e35feb74`
- Контракт: `task_type=code`, `complexity=complex`, `risk=high`,
  `mutation_policy=isolated_pr_only`, `requested_tier=high_risk`

## Перед началом

### Цель

Переписать канонические context packs Каэля, Велвета и Макса так, чтобы
реализация coder, независимый review, merge authorization и rollout acceptance
были разными проверяемыми стадиями, а решение review опиралось на доверенные
evidence, effective workspace и bounded review-fix contract.

### Исходный контекст

PR #582 уже слит в базовый commit и реализует central router, disposable per-run
clone, read-only base checkout и mutation fingerprint. Issue #584 требует
канонизировать поведение трёх существующих сущностей без identity forks и
закрепить его behavioral/integration tests, а не только строковыми маркерами.

### Планируемый объём

- добавить исполняемый fail-closed review/readiness policy для Каэля;
- синхронизировать canonical SOUL/entity/policy/compiler inputs трёх сущностей;
- проверить direct/delegated identity и trusted ledger route/evidence boundaries;
- связать readiness review с effective workspace и mutation evidence;
- добавить behavioral/integration coverage и compiler/install/verify regression;
- не менять installed production context и runtime services.

### Requirement coverage matrix до изменения production-кода

| Requirement | Source / acceptance | Planned files / tests | Status before code |
|---|---|---|---|
| Readiness stages отделяют coder, review, merge и rollout | Issue §1, DoD | `review_gate.py`, `test_hermes_issue_584_behavior.py`, Kael canonical context | covered locally |
| Evidence hierarchy не позволяет слабому evidence подтверждать сильное | Issue §2 | review policy + behavioral tests + shared brain policy | covered locally |
| Каэль проверяет issue/changed-file/cross-component coverage и выдаёт approved/changes_requested/blocked | Issue §3 | review policy, `AGENTS.kael.md`, entity source, tests | covered locally |
| Велвет/Макс сохраняют одну identity для owner-direct и kael-delegated | Issue §4 | coder SOUL/entity sources, router integration tests | covered locally |
| Route/status/mutation fields принимаются только из ledger/runner | Issue §4, §7, §15 | review policy trusted evidence input, coder contexts, negative tests | covered locally |
| Cross-component изменения требуют integration evidence; static-only недостаточен для high-risk | Issue §5, §9 | review policy + negative/positive tests | covered locally |
| Engineering regression checklist канонический | Issue §6 | brain policy + context sources/compiler manifest | covered locally |
| Ответы разделяют verified claims/findings/rollout gaps | Issue §7 | Kael context + review decision contract tests | covered locally |
| Compile/install/final verify сохраняют hashes, atomicity и private permissions | Issue §8–9 | existing brain runtime + extended integration test | covered locally |
| Rollout checks не закрываются локально | Issue §10 | review policy negative tests + canonical contexts | covered locally; host pending |
| Effective cwd совпадает с ledger workspace; shared base fail-closed | Issue §11, §15 | existing tier runner + integration regression tests | covered locally |
| Mutation audit остаётся true после clean commit/HEAD/ref change и является OR trusted signals | Issue §12, §15 | existing tier runner + direct behavioral regression tests | covered locally |
| Ledger/GitHub conflict блокирует approval | Issue §13 | review policy + negative tests | covered locally |
| После двух review-fix циклов автоматическая делегация прекращается | Issue §14–15 | review policy + boundary tests | covered locally |
| Cleanup ограничен каталогом run | Issue §15 | existing tier runner + behavioral regression test | covered locally |
| Ровно три canonical operational entities без direct/delegated forks | DoD | manifest/entity/compiler contract tests; Librarian остаётся отдельным deny-all utility profile | covered locally |

### Критерии готовности

Все строки matrix имеют behavioral либо integration evidence; brain packs
проходят validate/compile/install/verify; relevant Hermes suite и project notes
contract зелёные; exact PR head проходит независимый high-risk review и CI.

### Риски и ограничения

Изменение управляет существующим Hermes engineering workflow и не добавляет
предметную область. Сохраняются три operational identity, project isolation,
read-only base, no-production-privileges и owner authorization для merge/rollout.
Host installation, restart, direct/delegated live dry-run и production checkout
cleanliness являются rollout-only и локально не закрываются.

### Stabilization gate

1. Улучшается существующий coder/review workflow Hermes.
2. Review становится fail-closed, наблюдаемым и ограниченным двумя fix-циклами.
3. Новая предметная область не появляется: меняется engineering control plane.
4. Улучшение проверяется behavioral/integration и context integrity tests.
5. Сохраняются repository, identity, privilege и rollout boundaries.

## После завершения

### Фактически сделано

- добавлен исполняемый review gate со стадиями readiness, evidence hierarchy,
  requirement/changed-file coverage и fail-closed conflict handling;
- direct handoff больше не содержит static `workspace=/workspace`, а требует
  effective per-run workspace runner;
- canonical SOUL/AGENTS/entity/handoff packs трёх operational identity и общий
  engineering evidence checklist синхронизированы через brain manifest v2;
- behavioral tests покрывают green-CI pending, findings, static-only rejection,
  identity parity, trusted route fields, workspace mismatch, clean commit
  mutation, evidence conflict и review-fix limit;
- integration test компилирует, устанавливает и проверяет packs Каэля, Велвета
  и Макса, hashes и private permissions после финальной записи.

### Миграции и совместимость

Миграций БД нет. Router payload сохраняет schema, но удаляет недостоверный
статический workspace path; effective path по-прежнему inject-ится tier runner.
Velvet Librarian остаётся отдельным deny-all utility profile и не создаёт новую
coder/operator identity. Installed production contexts не изменялись.

### Проверки

- `python -m unittest tests.test_hermes_issue_584_behavior tests.test_hermes_codex_tier_runner tests.test_hermes_issue_581_contract tests.test_hermes_brain_vault` — 40 tests OK, 1 optional environment skip;
- `python deploy/hermes-brain/context_compiler.py validate` — OK, 4 manifest profiles / 30 vault files;
- compile/verify `kael`, `velvet-coder`, `max-coder` во временном каталоге — OK;
- `python scripts/ci_preflight.py` — 8 architecture/navigation tests OK;
- `python -m compileall -q deploy/hermes-operator deploy/hermes-coders deploy/hermes-brain tests/test_hermes_issue_584_behavior.py` — OK;
- full `test_hermes*.py` discovery: 181 passed, 1 skipped, collection одного
  unrelated storage-librarian test blocked отсутствующим `asyncpg` в isolated image;
- `git diff --check` — OK.

### PR и commit

Implementation commit, exact head и PR будут добавлены после commit/push.
Автоматических review-fix циклов на этом срезе: 0.

### Незавершённое

- независимый high-risk review exact head и terminal GitHub CI;
- после merge: atomic context install, manifest/permissions verify, необходимые
  service restarts, live identity direct/delegated dry-runs, defective-PR rejection
  и production checkout cleanliness — только owner-authorized rollout.

### Следующий шаг

Создать один implementation commit и PR, выполнить независимый review exact
head, исправляя findings максимум двумя циклами в существующем PR, затем дождаться
terminal CI. Merge и rollout не выполнять.
