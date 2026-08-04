# Сессия: release-bound systemd lifecycle Hermes coders

- Дата: `2026-08-05`
- ID: `hermes-release-systemd-lifecycle-20260805`
- Линия/фаза: `server operations / Hermes coder release`
- Статус: `частично`
- Ветка: `fix/hermes-release-systemd-lifecycle`
- Базовый commit: `c5685fc117c9c622afc955287f0cae5b9d5dae81`
- Связанные issue и release evidence: `#592`, `#581`, `#611`, `#620`

## Перед началом

### Цель

Закрыть разрыв между успешно выпущенными Hermes coder контейнерами и systemd,
который продолжал использовать mutable checkout `/srv/velvet` и оставался в
состоянии `failed/inactive` после старого startup smoke.

### Подтверждённое production-состояние

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

### Ограничения

- не использовать `docker compose down` или `down -v`;
- не удалять auth, ledger, runs, workspaces, secrets или volumes;
- не выполнять production rollout и merge без отдельного разрешения владельца;
- не ослаблять AppArmor, seccomp, `NoNewPrivs`, capability или read-only rootfs;
- сохранить exact-main detached release и rollback contract.

## Реализация

### Release-bound units

Оба systemd unit переведены на:

```text
/srv/hermes-coders/releases/current-hermes-coders
```

Обычный start/reload использует fixed Compose project names и `--no-build`, чтобы
reboot не собирал images и не возвращался к mutable `/srv/velvet`.

### Startup smoke

`runtime_smoke.py`:

- использует абсолютные Compose paths и project name `hermes-coders`;
- получает default branch через authenticated GitHub API `.default_branch`;
- сохраняет обязательные userns, mountns, bwrap read-only/write, AppArmor,
  seccomp, capability, rootfs и zombie checks;
- отделяет nested bubblewrap `/proc` probe в explicit strict mode
  `HERMES_CODEX_STRICT_NESTED_PROC_SMOKE=1`;
- systemd startup использует strict mode `0`.

`tier_provider_smoke.py` и `router_smoke.py` используют абсолютные Compose paths
и fixed project names, поэтому запускаются из любого каталога.

### Systemd reconciler

Добавлен root-only `deploy/hermes-coders/reconcile_release_systemd.sh`.
Он проверяет exact release SHA, резервирует старые unit/drop-in/override, ставит
release-bound units, очищает stale failed state, запускает или reload-ит oneshot
units, выполняет все smoke и проверяет container health. Legacy override
перемещается в backup только после полного успеха. При ошибке unit-файлы
восстанавливаются, уже работающие контейнеры не удаляются и не останавливаются.

## Проверки

Добавлены или обновлены contract tests для:

- отсутствия `/srv/velvet/deploy/hermes-*` в unit-файлах;
- approved release symlink в coder/router lifecycle;
- absolute Compose paths и fixed project names;
- GitHub API default branch вместо `ls-remote | sed`;
- optional strict nested `/proc` probe;
- non-destructive systemd reconciler и backup contract;
- runtime/provider/router smoke paths после start/reload.

Required CI и production rollout ещё не выполнены.

## Rollout после merge

1. Выпустить точный актуальный `main` через `release/hermes-coders-<sha>`.
2. Получить `Outcome: success` в issue `#592`.
3. Запустить один раз:

```bash
release_dir="$(readlink -f /srv/hermes-coders/releases/current-hermes-coders)"
sudo env HERMES_CODERS_ROOT=/srv/hermes-coders \
  bash "$release_dir/deploy/hermes-coders/reconcile_release_systemd.sh"
```

4. Подтвердить `active/exited/0` для coder и router units.
5. Повторить health, два read-only handoff и zombie checks.
6. Не удалять backup directory до следующего успешного reboot/restart smoke.

## Незавершённое

- дождаться required CI;
- устранить возможные contract failures;
- review и merge требуют отдельного разрешения;
- exact-main release и systemd reconciliation требуют отдельного разрешения;
- после rollout обновить статус worklog на `завершено` с release SHA и evidence.
