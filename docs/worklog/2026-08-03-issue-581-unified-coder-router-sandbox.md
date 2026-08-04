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

Будут записаны после commit/push/создания единственного PR.

### Незавершённое

Нужны независимый review, GitHub CI и отдельный approved live rollout с четырьмя
Telegram paths. Временный production workaround этим PR не удаляется.

### Следующий шаг

Завершить review, создать один commit/PR в main и дождаться terminal CI status.
