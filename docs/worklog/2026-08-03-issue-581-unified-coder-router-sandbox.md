# Сессия: единый coder-router и постоянный sandbox

- Дата: 2026-08-03
- ID: `7a07bac17fcc4d2d95ed651bfcd80e3b`
- Линия/фаза: hotfix/эксплуатация вне фаз
- Статус: частично
- Issue: #581
- Ветка: `hotfix/581-unified-coder-router-sandbox`
- Базовый commit: `eb4849c3ee4461b540d3e1ba0572cf54f82a12d3`

## Перед началом

### Цель

Закрепить единый fail-closed central router для direct/delegated coder-задач и
repository-managed enforcing sandbox/lifecycle contract для обоих runner.

### Исходный контекст

После #576 delegated path сохранял tier metadata, но direct Telegram helper
обращался непосредственно к runner. Compose не имел постоянного AppArmor/seccomp
layer, а oneshot installer не гарантировал restart уже active/exited unit.

### Планируемый объём

- перевести direct helper на central router с `source=owner-direct`;
- закрепить identity parity, реальные task/run IDs и fail-closed contract;
- добавить AppArmor, seccomp, единые compose layers и sandbox smoke;
- исправить atomic context verification, temp cleanup и oneshot verification;
- добавить cryptography 50.0.0 check и regression tests.

### Критерии готовности

Focused contract/sandbox tests проходят для Velvet и Max; compose render содержит
runtime/security layers; direct path не имеет local fallback; обязательные project
checks и CI зафиксированы; production не изменяется.

### Риски и ограничения

Live AppArmor, userns, bwrap, systemd и Telegram проверки доступны только после
отдельного approved rollout. В PR проверяются render/contract и безопасные probes.

Изменение повышает надёжность существующей coder-инфраструктуры, не добавляет
предметную область. Сохраняются non-root, read-only rootfs, cap-drop, отсутствие
Docker socket/production volumes и запрет production privileges.

## После завершения

### Фактически сделано

- direct Telegram helper переведён с local runner на central tier router с
  `source=owner-direct`, task ID и fail-closed token contract;
- delegated CLI использует `source=kael-delegated`; router handoff фиксирует
  canonical identity `Велвет`/`Макс`;
- каждый run получает disposable clone от актуальной default branch;
- shared base checkout монтируется read-only и не является task workspace;
- runner записывает effective per-run cwd в ledger и добавляет его в execution
  context непосредственно перед запуском модели;
- mutation audit учитывает HEAD, branch, refs, working tree, shared base и
  branch/PR evidence, поэтому clean status после commit не маскирует mutation;
- добавлены enforcing AppArmor, Docker-default-based seccomp и третий Compose
  security layer;
- installer и systemd используют одинаковые три lifecycle layer, restart oneshot
  и проверку `active/exited/0`;
- context installer верифицирует manifest после последней atomic записи;
- orchestration installer вызывает один canonical coder reconcile и устанавливает
  Каэля через compiler/install/verify без ручной перезаписи managed `SOUL.md`;
- runtime smoke разделяет read-only base probe и writable disposable-run probe,
  проверяет namespaces/security/fingerprint и `cryptography==50.0.0`.

### Миграции и совместимость

Миграций БД нет. Direct helper теперь требует central router client token и не
совместим с прямым обращением к runner; это намеренный fail-closed контракт.

Codex task checkout изменён с общего `/workspace` на dynamic path внутри
`/opt/codex-runs/<project>/workspaces/<run_id>`. `/workspace-base` доступен только
как read-only источник для создания disposable clone.

### Проверки первоначальной реализации

- `python -m unittest` focused Hermes set: 76 tests — OK после обновления одного
  устаревшего lifecycle expectation;
- `python -m unittest discover -s tests -p 'test_hermes*.py'`: 161 tests прошли,
  один unrelated module collection был заблокирован отсутствующим `asyncpg` в
  isolated coder image;
- focused contract set: 74 tests — OK, включая project notes;
- `git diff --check`, `bash -n`, `compileall` — OK;
- Docker/AppArmor/systemd/Telegram live smoke не запускались: production и Docker
  были запрещены контрактом задачи.

### PR и commit

- PR: #582;
- implementation commit: `1c918234dbe55674eb652dbb22064e83deeb010a`;
- первый reviewed head: `c1772ade7062208644da9b4d77ec5b393cac828d`;
- первый coder review-fix head: `f8980f1e6477c79d53a71eb7637ea64bc1fe45e7`.

### Blocking review 4849528520

Первый независимый review выявил несовместимые direct/router schemas, duplicate
`security_opt`, незамкнутый router token, не исправленный orchestration installer,
неверный main-Hermes probe, нерабочий bwrap smoke, handcrafted seccomp, неполный
AppArmor и hardcoded `origin/main`.

Исправлено в существующем PR:

- direct payload проходит integration path
  `codex_delegate -> HTTP Handler -> TierAwareCoderRouter -> mocked upstream`;
- routing metadata сохраняется до runner;
- security overlay не дублирует `no-new-privileges`;
- реальный three-layer Compose render проходит `config --quiet`;
- router client token выводится из `HERMES_OPS_CLIENT_TOKEN` и передаётся обоим
  direct coder env без вывода значения;
- canonical server Compose и service `hermes` используются для cryptography probe;
- seccomp основан на Docker default с ограниченной userns clone rule;
- AppArmor содержит mount propagation, proc, bind и confined project execution;
- default branch получается из remote metadata и валидируется.

### Blocking review 4849624310 и независимый fix pass

Второй review был вызван противоречием: remote PR head изменился, но ledger
continuation-run сообщил `mutation_started=false`.

Причина локализована в execution workspace contract:

- runner создавал isolated worktree и считал fingerprint в нём;
- router и compiled AGENTS продолжали направлять модель в `/workspace`;
- общий checkout оставался writable;
- commit/push мог происходить вне контролируемого path.

По распоряжению владельца автоматический цикл Каэль → coder остановлен. Дальнейшие
изменения внесены независимым исполнителем в ту же branch и тот же PR.

Исправления:

- Git worktree заменён на disposable clone, не требующий writable shared `.git`;
- base checkout монтируется как `/workspace-base:ro`;
- legacy `/workspace` отсутствует у Codex runner;
- router и coder AGENTS требуют работать только в current runner cwd;
- effective `workspace_path`, source ref и baseline HEAD сохраняются в ledger;
- snapshot включает HEAD, branch, refs и working tree;
- base checkout snapshot проверяется отдельно;
- commit с последующим clean status покрыт behavioral test;
- read-only commit отклоняется даже при clean final status;
- изменение base checkout завершается fail-closed;
- cleanup удаляет только clone конкретного run;
- runtime smoke отдельно доказывает read-only base и writable per-run clone;
- AppArmor разрешает inherited execution только внутри disposable run tree;
- orchestration install больше не выполняет ранний preflight и не редактирует
  manifest-managed Hermes `SOUL.md` вручную;
- Kael context устанавливается только через brain compiler/install/verify.

Issue #584 дополнен обязательными правилами effective workspace, evidence conflict,
mutation evidence и максимумом двух автоматических review-fix итераций.

### CI независимого fix pass

- preflight, type check, project notes, Hermes monitor/reconcile и три test shards
  прошли на промежуточном head;
- первый CI выявил устаревший exact-string read-only contract. Он заменён проверкой
  фактического поведения: assigned runner cwd, запрет Git mutation и отсутствие
  static `workspace=/workspace`;
- точный финальный head и полный terminal CI фиксируются перед merge recommendation;
- live AppArmor/systemd/bwrap/Telegram проверки остаются rollout-only.

### Незавершённое

- дождаться terminal CI на точном финальном head;
- выполнить отдельный approved live rollout;
- проверить enforcing AppArmor и custom seccomp на production host;
- выполнить direct/delegated read-only paths для Велвета и Макса;
- выполнить mutation-audit smoke с test branch/PR без merge;
- удалить временный `seccomp=unconfined`/unconfined AppArmor workaround только после
  успешного постоянного sandbox acceptance.

### Следующий шаг

После terminal CI и owner review подготовить controlled rollout точного merge SHA.
Merge, deploy, restart production и удаление временного workaround выполняются
только по отдельному разрешению владельца.
