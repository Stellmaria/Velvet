# Сессия: canonical host sandbox launcher для Hermes coders

- Дата: `2026-08-05`
- ID: `hermes-host-sandbox-launcher-v2-20260805`
- Линия/фаза: `Hermes security / canonical execution backend`
- Статус: `в работе`
- Ветка: `feat/594-host-sandbox-launcher-v2`
- Базовый commit: `c5685fc117c9c622afc955287f0cae5b9d5dae81`
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
заново от актуального `main`.

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
- добавлены behavioral и deployment tests.

### Миграции и совместимость

- database migrations отсутствуют;
- Runs API и router payload не меняются;
- project/tier/provider routing не переносится в launcher;
- ledger, terminal state, workspace clone и mutation audit остаются в текущем
  runner;
- production services и compatibility override этой кодовой сессией не менялись.

### Проверки

- Python syntax и focused tests будут запущены после публикации первого реального
  commit в ветку;
- Docker Compose contract будет проверен с synthetic env fixtures;
- required GitHub CI будет проверяться только на точном head;
- live AppArmor, socket, canary, reboot и rollback остаются rollout-only.

### PR и commit

- PR: `не открыт до публикации первого реального commit`;
- base: `c5685fc117c9c622afc955287f0cae5b9d5dae81`;
- head: `будет зафиксирован после atomic Git tree commit`;
- merge commit: `отсутствует`;
- production SHA: `не менялся`.

### Незавершённое

- собрать atomic tree и опубликовать первый head;
- открыть draft PR;
- исправить exact-head CI;
- обновить canonical coder installer и release workflow;
- выполнить independent review;
- получить отдельное merge approval;
- выполнить staged rollout и live acceptance;
- удалить compatibility override только после полного PASS.

### Следующий шаг

Опубликовать реальный первый commit с launcher core и behavioral contracts,
проверить compare `ahead_by > 0`, открыть draft PR и разбирать CI по точному head.
