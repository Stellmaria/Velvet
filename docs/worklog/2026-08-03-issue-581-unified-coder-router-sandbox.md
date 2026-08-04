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
- каждый run получает отдельный worktree от свежего `origin/main`, mutation
  fingerprint и scoped cleanup audit;
- добавлены enforcing AppArmor, allowlist seccomp и третий Compose security layer;
- installer и systemd используют одинаковые три lifecycle layer, restart oneshot
  и проверку `active/exited/0`;
- context installer верифицирует manifest после последней atomic записи;
- runtime smoke проверяет namespaces/bwrap/security/fingerprint и
  `cryptography==50.0.0`.

### Миграции и совместимость

Миграций БД нет. Direct helper теперь требует central router client token и не
совместим с прямым обращением к runner; это намеренный fail-closed контракт.

### Проверки

- `python -m unittest` focused Hermes set: 76 tests — OK после обновления одного
  устаревшего lifecycle expectation;
- `python -m unittest discover -s tests -p 'test_hermes*.py'`: 161 tests прошли,
  один unrelated module collection заблокирован отсутствующим `asyncpg` в образе;
- финальный focused contract set: 74 tests — OK, включая project notes;
- `git diff --check`, `bash -n`, `compileall` — OK;
- независимый high-risk review выявил и помог исправить inherited fingerprint
  helper collision, incomplete AppArmor execute rules и неверные namespace/proc probes;
- Docker/AppArmor/systemd/Telegram live smoke не запускались: production и Docker
  запрещены контрактом задачи.

### PR и commit

- PR: #582;
- implementation commit: `1c918234dbe55674eb652dbb22064e83deeb010a`;
- CI для implementation commit: все 19 checks terminal, 18 pass и один
  ожидаемый CodeQL wrapper `skipping` после успешных `codeql-actions/python`.

### Незавершённое

Нужен отдельный approved live rollout с четырьмя Telegram paths. Временный
production workaround этим PR не удаляется.

### Blocking review 4849528520 — исправление 4 августа 2026

- direct payload теперь проходит integration path
  `codex_delegate -> HTTP Handler -> TierAwareCoderRouter -> mocked upstream` и
  сохраняет все пять routing-полей до runner;
- security overlay больше не дублирует `no-new-privileges`; реальный Compose
  v2.39.1 render трёх layers проходит `config --quiet`;
- единственный router client token выводится из `HERMES_OPS_CLIENT_TOKEN`,
  записывается без печати значения в router env и оба direct coder env;
- orchestration installer использует runtime/security layers, устанавливает
  manifest-managed coder context с режимом `0600`, не перезаписывает coder
  `SOUL.md` после manifest и выполняет verify после последней записи;
- lifecycle явно перезапускает coder, router и incident oneshot units;
- cryptography probe использует `.env.server`, canonical server Compose и
  service `hermes`; bwrap probe реально исполняет Git с доступным root tree;
- seccomp заменён актуальной Docker-default основой с минимальными bwrap
  additions; AppArmor дополнен mount propagation/proc/bind и project-tool exec;
- isolated worktree получает и валидирует default branch из remote metadata,
  без hardcoded `origin/main`.

Проверки review-среза: focused Hermes — 60 tests OK; полный релевантный Hermes
suite без импортирующего отсутствующий в runner `asyncpg` entity-contract —
165 tests OK, 1 environment skip; `compileall`, `bash -n`, JSON parse,
`git diff --check` — OK; standalone Docker Compose v2.39.1 three-layer
`config --quiet` — OK. Docker daemon, AppArmor parser/audit и live container
smoke недоступны в isolated coder contract и остаются rollout-only проверками.

### Следующий шаг

После owner review слить PR #582; затем отдельным разрешённым rollout выполнить
AppArmor/systemd/bwrap и четыре Telegram smoke до удаления workaround.
