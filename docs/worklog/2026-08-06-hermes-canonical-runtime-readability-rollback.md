# Сессия: Hermes canonical runtime readability and rollback

- Дата: `2026-08-06`
- ID: `hermes-canonical-runtime-readability-rollback-20260806`
- Линия/фаза: `server operations / Hermes coder canonical production release`
- Статус: `частично`
- Ветка: `fix/hermes-canonical-runtime-readability-rollback`
- Базовый commit: `2b43562f67ea167e47a4167432bb9c07e484580d`
- Связанные issue, PR и release evidence: `#592`, `#638`, release run `31048424514`, production rollback bundle `issue-594-20260805T212931Z-2b43562f67ea167e47a4167432bb9c07e484580d`

## Перед началом

### Цель

Устранить подтверждённый restart-loop canonical Hermes coders и сделать rollback
транзакционным относительно Docker images и legacy systemd override.

### Исходный контекст

Canonical release `2b43562f67ea167e47a4167432bb9c07e484580d` успешно прошёл
exact-main, idle, Brain Vault, launcher authentication, immutable image и sandbox
preflight. После переключения release symlink `hermes-coders.service` пересоздал
оба coder containers, но `runtime_smoke.py` дождался restart-loop и завершился
через 180 секунд.

Production journal и exact release graph подтвердили причину:

- `compose.runtime.yaml` bind-mounts `codex_image_runner.py` в оба coder services;
- `codex_context_launcher_runner.py` импортирует `codex_image_runner` при startup;
- detached release worktree создаётся workflow под `umask 077`;
- `runtime_source_guard.py` и systemd chmod preflight забыли
  `codex_image_runner.py`;
- root-side import preflight прочитал mode `0600`, а container UID `10000` не смог;
- AppArmor DENIED отсутствовали.

Rollback вернул предыдущий release link и рабочие containers, но не смог
восстановить прежние image IDs после перезаписи local tags во время build. Затем
старый Compose был пересоздан на новых images. Runtime восстановился как healthy,
но image-exact rollback contract был нарушен. Legacy drop-in
`20-bwrap-runtime.conf` также оставался подключённым к canonical unit.

### Планируемый объём

- добавить `codex_image_runner.py` в runtime permission guard и import probe;
- добавить файл в systemd chmod preflight для start и reload;
- regression-test соответствие Python bind mounts permission guard;
- сохранить прежние coder images отдельными rollback tags до build;
- запретить rollback recreation при отсутствии exact previous images;
- backup/remove/restore legacy systemd drop-in транзакционно;
- не менять volumes, auth, ledger, workspaces, secrets или database state;
- слить только после зелёного required CI.

### Критерии готовности

- release-bound image runner читается container UID до Compose recreation;
- полный local import graph проходит до production switch;
- canonical activation не наследует legacy bwrap drop-in;
- failed release может вернуть exact previous coder images;
- rollback не запускает старый Compose на случайных current local tags;
- tests, type check, notes, security, Docker и protection contracts зелёные.

### Риски и ограничения

- production пока остаётся на legacy security override с healthy containers;
- `hermes-coders.service` не должен запускаться до нового exact-main release;
- GitHub deploy workflow по-прежнему не имеет разрешённого non-interactive sudo;
- временные compatibility files удаляются только после успешной canonical проверки.

## После завершения

### Фактически сделано

- `codex_image_runner.py` добавлен в `RUNTIME_SOURCES` и direct import probe;
- systemd start/reload permission preflight включает image runner;
- regression contract извлекает все Python bind mounts из Compose и требует их
  покрытия guard;
- release создаёт unique rollback tags для обоих live coder image IDs до build;
- rollback восстанавливает canonical local tags только из сохранённых tags;
- при отсутствии exact rollback image recreation fail-closes;
- legacy `20-bwrap-runtime.conf` включён в artifact backup, удаляется перед
  canonical install и восстанавливается rollback при необходимости;
- shell syntax release script проверяется тестом.

### Риски и ограничения

- production acceptance ещё не выполнен;
- runtime systemd unit остаётся отключённым до нового release;
- workflow sudo contract требует отдельного ограниченного privileged entrypoint;
- старые temporary override files остаются evidence до canonical success.

### Миграции и совместимость

- database migrations отсутствуют;
- persistent volumes, auth, runs, workspaces и secrets не изменяются;
- compatibility override разрешён только в rollback подтверждённого legacy runtime;
- successful release удаляет только временные rollback image tags.

### Проверки

Добавлены проверки для:

- двух mounts `codex_image_runner.py`;
- покрытия каждого Python runtime mount permission guard;
- direct import image runner в release graph;
- systemd chmod coverage;
- rollback image tags и fail-closed recreation;
- removal legacy drop-in;
- `bash -n deploy/hermes-coders/release.sh`.

### PR и commit

- ветка: `fix/hermes-canonical-runtime-readability-rollback`;
- base: `2b43562f67ea167e47a4167432bb9c07e484580d`;
- PR и merge commit фиксируются после required CI.

### Незавершённое

- проверить diff и targeted tests;
- дождаться всех required CI contexts;
- исправить только подтверждённые failures;
- выполнить штатный squash merge;
- выпустить fresh exact-current-main release;
- подтвердить canonical AppArmor, launcher и healthy/restarts=0;
- удалить temporary compatibility files после acceptance.

### Следующий шаг

Открыть draft PR, пройти required CI, затем выполнить новый exact-current-main
release только при idle runtime и неизменном main.
