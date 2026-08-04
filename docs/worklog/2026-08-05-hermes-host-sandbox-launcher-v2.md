# Сессия: canonical host sandbox launcher для Hermes coders

- Дата: `2026-08-05`
- ID: `hermes-host-sandbox-launcher-v2-20260805`
- Линия/фаза: `Hermes security / canonical execution backend`
- Статус: `частично`
- Ветка: `feat/594-host-sandbox-launcher-v2`
- Базовый commit при старте: `c5685fc117c9c622afc955287f0cae5b9d5dae81`
- Текущая база PR после синхронизации: `88540a17ef32a69ce7470ab2f48afcb5552e054a`
- Связанные issue: `#594`, `#581`, `#584`, `#595`

## Перед началом

### Цель

Заменить неработающий nested-bwrap contract на один проверяемый security boundary:
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
- installer/preflight/runtime smoke;
- behavioral и deployment contracts;
- обновление exact-main Hermes release workflow;
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
- текущий release workflow умеет пересоздавать только coder containers и должен
  быть расширен до atomic launcher activation;
- compatibility override сохраняется для rollback до завершения live acceptance;
- database migrations и основной bot stack в эту работу не входят.

## После завершения

### Фактически сделано

- создана новая ветка от exact current `main`;
- опубликован реальный draft PR `#629` с 22 changed files;
- подготовлен fixed-schema launcher contract;
- Docker command вычисляется launcher-ом и не принимает arbitrary arguments;
- добавлены route/model matrix, path/symlink validation и scoped env files;
- добавлены separate timeout/cancellation semantics и stale cleanup;
- systemd server использует socket activation, peer UID check и bounded
  connection capacity;
- Codex home копируется через explicit allowlist, provider route не получает
  subscription auth;
- canonical runner adapter сохраняет существующий control plane;
- local rollback требует отдельного operator gate;
- подготовлены AppArmor profiles, socket/service units, installer и preflight;
- добавлены behavioral и deployment tests;
- ветка синхронизирована с продвинувшимся `main` merge-коммитом;
- первый exact-head CI выявил два совместимых дефекта: устаревший bwrap contract
  и удалённый helper `verify_github_access`; оба исправляются одним correction
  commit.

### Миграции и совместимость

- database migrations отсутствуют;
- Runs API и router payload не меняются;
- project/tier/provider routing не переносится в launcher;
- ledger, terminal state, workspace clone и mutation audit остаются в текущем
  runner;
- production services и compatibility override этой кодовой сессией не менялись.

### Проверки

- preflight Python compilation прошла;
- exact-head type check прошёл;
- project notes потребовал допустимый статус и исправлен на `частично`;
- test shards выявили устаревшие runtime-smoke contracts, исправленные в
  correction commit;
- Docker, security и branch-protection checks будут оцениваться только на новом
  exact head;
- live AppArmor, socket, canary, reboot и rollback остаются rollout-only.

### PR и commit

- PR: `#629`;
- первый implementation commit: `8eb6ff42b70eeeb1f4a0078638257609d9ed12c2`;
- merge current main commit: `1d9bcdefc4002cea4dd3c0bf87a35f3ad60cf3bd`;
- новый exact head будет определён correction commit;
- merge commit в `main`: `отсутствует`;
- production SHA: `не менялся`.

### Незавершённое

- получить зелёный exact-head CI для launcher core;
- интегрировать launcher installer в canonical coder installer;
- обновить exact-main Hermes release workflow;
- выполнить independent review;
- получить отдельное merge approval;
- выполнить staged rollout и live acceptance;
- удалить compatibility override только после полного PASS.

### Следующий шаг

Опубликовать correction commit для runtime-smoke compatibility и worklog,
дождаться exact-head CI, затем замкнуть canonical installer и release workflow.
