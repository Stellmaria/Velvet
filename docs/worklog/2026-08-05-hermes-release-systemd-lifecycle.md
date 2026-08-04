# Сессия: release-bound systemd lifecycle Hermes coders

- Дата: `2026-08-05`
- ID: `hermes-release-systemd-lifecycle-20260805`
- Линия/фаза: `server operations / Hermes coder release`
- Статус: `частично`
- Ветка: `fix/hermes-release-systemd-lifecycle`
- Базовый commit: `c5685fc117c9c622afc955287f0cae5b9d5dae81`
- Связанные issue, PR и release evidence: `#592`, `#581`, `#611`, `#620`, `#626`

## Перед началом

### Цель

Закрыть разрыв между успешно выпущенными Hermes coder контейнерами и systemd,
который продолжал использовать mutable checkout `/srv/velvet` и оставался в
состоянии `failed/inactive` после старого startup smoke.

### Исходный контекст

Exact release `bfda60395fe03b83b8b62f47707994e870ff691a` успешно выпущен.
Оба coder-контейнера подтверждены как `running`, `healthy`, restart count `0` и
`init=true`. Реальные read-only задачи Velvet и Max завершились через
`codex_subscription:gpt-5.6-luna`, не изменили HEAD, refs или working tree и не
создали push/PR. Host и container zombie counts равны нулю.

При этом:

- `hermes-coders.service` оставался `failed` из-за старого nested bubblewrap
  `/proc` probe;
- `hermes-coder-router.service` оставался `inactive` из-за зависимости от failed
  coder unit;
- оба unit-файла ссылались на `/srv/velvet/deploy/...`, а не на exact release;
- `tier_provider_smoke.py` и `router_smoke.py` зависели от текущего каталога;
- `runtime_smoke.py` извлекал default branch через хрупкий `ls-remote | sed` и на
  production получил недопустимое имя `?`.

### Планируемый объём

- привязать coder/router units к approved release symlink;
- исключить rebuild и возврат к mutable checkout при reboot/start/reload;
- сделать три smoke независимыми от текущего каталога;
- заменить хрупкое определение default branch на authenticated GitHub API;
- отделить nested `/proc` qualification probe от обязательного startup smoke;
- добавить root-only backup/rollback reconciler для one-time migration systemd;
- покрыть изменения contract tests и release documentation;
- не выполнять merge, release или production reconciliation в рамках PR.

### Критерии готовности

- unit-файлы не содержат `/srv/velvet/deploy/hermes-*`;
- coder и router lifecycle используют `current-hermes-coders`;
- Compose project names фиксированы, пути smoke абсолютные;
- normal startup сохраняет обязательные sandbox checks, но не блокируется на
  дополнительном nested `/proc` mount;
- strict nested `/proc` diagnostic остаётся доступным явно;
- reconciler резервирует прежнюю конфигурацию и не использует `compose down`;
- при ошибке reconciler возвращает два coder-контейнера к ранее смонтированному
  Compose source без удаления volumes;
- CI проходит на PR merge ref;
- production rollout выполняется только после отдельного разрешения.

### Риски и ограничения

- systemd migration требует root и отдельного ручного запуска после exact-main
  release;
- старые units/drop-in нельзя удалять без backup;
- active release worktree нельзя удалять, пока из него bind-mounted runtime files;
- `--no-build` на reboot предполагает, что release workflow заранее подтвердил
  существующие image IDs;
- rollback может force-recreate только два coder-контейнера, но не использует
  `compose down` и не затрагивает persistent data;
- nested `/proc` diagnostic остаётся отдельным инфраструктурным сигналом и не
  выдаётся за исправленный AppArmor host limitation;
- auth, ledger, runs, workspaces, secrets и volumes должны быть сохранены.

## После завершения

### Фактически сделано

- оба systemd unit переведены на
  `/srv/hermes-coders/releases/current-hermes-coders`;
- start/reload используют fixed Compose project names и `--no-build`;
- `runtime_smoke.py` использует absolute Compose paths и GitHub API
  `.default_branch`;
- обязательные userns, mountns, bwrap read-only/write, AppArmor, seccomp,
  capability, rootfs, auth, push dry-run, fingerprint и zombie checks сохранены;
- nested bubblewrap `/proc` probe вынесен в
  `HERMES_CODEX_STRICT_NESTED_PROC_SMOKE=1`, normal systemd startup использует `0`;
- `tier_provider_smoke.py` и `router_smoke.py` стали cwd-independent;
- добавлен `reconcile_release_systemd.sh` с exact-SHA validation, backup,
  stale-failed reset, smoke и container acceptance;
- перед изменениями reconciler фиксирует ранее смонтированный Compose source;
- при ошибке rollback восстанавливает unit/drop-in и force-recreate только два
  coder-контейнера из предыдущего Compose source с прежним override;
- legacy drop-in удаляется из active systemd только после backup;
- legacy Compose override переносится в backup только после полного успеха;
- обновлены release docs и regression tests;
- открыт draft PR `#626`.

### Риски и ограничения

- production всё ещё работает на ранее успешном release и пока сохраняет старое
  красное состояние systemd;
- PR не исправляет host kernel/AppArmor способность выполнять nested `/proc`
  mount, а корректно отделяет этот diagnostic от startup readiness;
- one-time reconciler ещё не выполнялся на production;
- окончательная проверка reboot/start lifecycle возможна только после merge,
  exact-main release и отдельного разрешения владельца.

### Миграции и совместимость

- database migrations отсутствуют;
- Velvet bot, PostgreSQL, supervisor, Krita и application stack не меняются;
- Docker volumes и persistent coder data не удаляются;
- существующие coder images переиспользуются на start/reload и rollback;
- release workflow и detached worktree contract сохраняются;
- rollback восстанавливает прежние unit-файлы, drop-in и ранее смонтированный
  runtime двух coder-контейнеров;
- новый normal smoke совместим с текущим production, где read-only/write bwrap
  probes проходят, а nested `/proc` probe отклоняется host policy.

### Проверки

Добавлены или обновлены contract tests для:

- отсутствия `/srv/velvet/deploy/hermes-*` в unit-файлах;
- approved release symlink в coder/router lifecycle;
- absolute Compose paths и fixed project names;
- GitHub API default branch вместо `ls-remote | sed`;
- optional strict nested `/proc` probe;
- non-destructive systemd reconciler и backup contract;
- rollback к ранее смонтированному coder Compose source;
- runtime/provider/router smoke paths после start/reload.

CI первого PR head выявил несоответствие структуры worklog; структура приведена к
canonical контракту. Следующие checks перезапускаются на каждом обновлённом head.

### PR и commit

- Draft PR: `#626`;
- ветка: `fix/hermes-release-systemd-lifecycle`;
- base при создании ветки: `c5685fc117c9c622afc955287f0cae5b9d5dae81`;
- актуальный PR head после safety-исправлений фиксируется GitHub;
- merge commit и production release SHA отсутствуют до отдельного разрешения.

### Незавершённое

- дождаться повторного required CI на новом head;
- устранить возможные code/test/contract failures;
- при необходимости синхронизировать ветку с новым `main` без потери scope;
- review и merge требуют отдельного разрешения;
- exact-main release и systemd reconciliation требуют отдельного разрешения;
- после rollout обновить статус на `завершено` с release SHA и evidence из #592;
- подтвердить следующий reboot/restart smoke перед удалением backup.

### Следующий шаг

Дождаться CI draft PR `#626`, исправить только подтверждённые failures и оставить
PR без merge и production действий до отдельного указания владельца.
