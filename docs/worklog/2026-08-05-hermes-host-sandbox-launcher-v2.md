# Сессия: canonical host sandbox launcher для Hermes coders

- Дата: `2026-08-05`
- ID: `hermes-host-sandbox-launcher-v2-20260805`
- Линия/фаза: `Hermes security / canonical execution backend`
- Статус: `частично`
- Ветка: `feat/594-host-sandbox-launcher-v2`
- Базовый commit: `c5685fc117c9c622afc955287f0cae5b9d5dae81`
- Текущая база PR: `55064cc0298962e616c3841644bcbd6e343a06ef`
- Связанные issue: `#594`, `#581`, `#584`, `#595`

## Перед началом

### Цель

Заменить неработающий nested-bwrap contract одним проверяемым security boundary:
root-owned Unix-socket launcher и отдельный disposable Docker container для
каждой попытки Codex, не переписывая router, tier policy, ledger, workspace
lifecycle и mutation audit.

### Исходный контекст

В `main` уже находятся central router, project identity parity, per-run remote
clone, terminal-state guards, mutation evidence и fail-closed делегирование
Каэля. Production compatibility path работает, но canonical
`hermes-coders.service` не принят из-за конфликтов nested user/mount namespaces,
Docker masked paths и AppArmor.

Предыдущая ветка `feat/594-host-sandbox-launcher` оказалась пустой: GitHub
показывал `ahead_by=0`, PR и exact-head CI отсутствовали. Реализация v2 начата
заново от актуального `main` и опубликована как реальный draft PR.

### Планируемый объём

- ADR и threat boundary;
- fixed-schema launcher protocol;
- root-owned fixed install directory;
- systemd socket activation;
- dedicated Docker network;
- disposable per-attempt container;
- route-scoped credential projection;
- отдельные AppArmor profiles runner/run;
- runner adapter без automatic local fallback;
- canonical installer/preflight/runtime smoke;
- exact-main versioned release script и rollback;
- behavioral и deployment contracts;
- отдельный staged production rollout после merge approval.

### Критерии готовности

- реальная ветка имеет commits и changed files;
- exact-head CI полностью зелёный;
- independent security/runtime review не содержит blockers;
- launcher не принимает command/image/mount/network/host path от caller;
- read-only task получает read-only workspace mount;
- provider task не получает subscription auth;
- runner не получает Docker socket;
- timeout не маркируется owner cancellation;
- retry блокируется после execution evidence даже при truncation;
- release workflow устанавливает exact launcher artifacts до переключения;
- merge и production rollout выполняются только после отдельного разрешения.

### Риски и ограничения

- root-owned launcher является новой доверенной поверхностью;
- Docker startup увеличивает latency каждой попытки;
- AppArmor и systemd hardening требуют live host проверки;
- compatibility override сохраняется только для rollback до live acceptance;
- database migrations и основной bot stack в эту работу не входят.

## После завершения

### Фактически сделано

- создана реальная ветка и draft PR `#629`;
- реализован fixed-schema launcher contract без arbitrary Docker arguments;
- добавлены route/model matrix, path/symlink validation и scoped env files;
- timeout отделён от owner cancellation;
- execution evidence вычисляется до output truncation;
- launcher использует systemd socket, peer UID check и bounded capacity;
- Codex home копируется через explicit allowlist;
- provider route не получает subscription auth;
- runner adapter сохраняет существующий control plane;
- local rollback требует отдельного operator gate;
- добавлены отдельные AppArmor profiles runner/run;
- launcher устанавливается из exact release root в root-owned fixed directory;
- `hermes-coders.service` использует stable exact-release symlink;
- canonical coder installer замыкает context, launcher, build, preflight и restart;
- release workflow передаёт управление versioned `release.sh` exact SHA;
- rollback сохраняет root artifacts, symlink и image identity;
- compatibility override используется только внутри rollback;
- добавлены behavioral, lifecycle и release contracts.

### Миграции и совместимость

- database migrations отсутствуют;
- Runs API и router payload не меняются;
- project/tier/provider routing не переносится в launcher;
- ledger, terminal state, workspace clone и mutation audit остаются в текущем
  runner;
- auth, ledger, runs, workspaces и secrets не удаляются rollback-ом;
- production services этой кодовой сессией не менялись.

### Проверки

- Python preflight compilation прошла на опубликованных heads;
- type check прошёл на `f22bf4c3ab2762b97c3abde9f3ea5e8331972698`;
- первый test run выявил устаревший bwrap contract и удалённый smoke helper;
- второй test run выявил неверный count command+mount и точное поле worklog;
- исправления и полный install/release contract включаются в следующий head;
- full exact-head CI, independent review и live host acceptance ещё не завершены.

### PR и commit

- PR: `#629`;
- первый implementation commit: `8eb6ff42b70eeeb1f4a0078638257609d9ed12c2`;
- merge-base sync commit: `1d9bcdefc4002cea4dd3c0bf87a35f3ad60cf3bd`;
- runtime compatibility commit: `f22bf4c3ab2762b97c3abde9f3ea5e8331972698`;
- следующий exact head: `будет зафиксирован после install/release commit`;
- merge commit в `main`: `отсутствует`;
- production SHA: `не менялся`.

### Незавершённое

- синхронизировать ветку с текущим `main`;
- получить полностью зелёный exact-head CI;
- провести independent security/runtime review;
- получить отдельное merge approval;
- выполнить staged rollout и live acceptance;
- удалить compatibility override только после полного PASS.

### Следующий шаг

Опубликовать install/release commit, проверить exact-head CI, исправить только
подтверждённые failures и передать готовый diff на независимый review.
