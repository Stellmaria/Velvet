# Сессия: Hermes smoke import и rollback environment

- Дата: `2026-08-06`
- ID: `hermes-smoke-rollback-env-20260806`
- Линия/фаза: `server operations / Hermes coder canonical production release`
- Статус: `частично`
- Ветка: `fix/hermes-smoke-rollback-env`
- Базовый commit: `76ce10d916e7901be6223534721e52adbd29dbe3`
- Связанные PR и release evidence: `#648`, `#649`, `#651`, deploy run `31051931525`

## Перед началом

### Цель

Устранить два независимых дефекта, обнаруженных canonical production release:
импорт launcher client из coder smoke и потерю launcher environment при rollback.

### Исходный контекст

Release `b0cef5fc2a62aff5b46d651bbcb10a926edbf42a` успешно собрал и запустил
оба canonical coder container с профилем `hermes-codex-runner`. Оба container
стабилизировались в `running/healthy/restarts=0`.

`hermes-coders.service` завершился ошибкой в `runtime_smoke.py`:

```text
ModuleNotFoundError: No module named 'sandbox_launcher_client'
```

Файл был корректно смонтирован в `/app`, но inline Python запускался из
`/opt/codex-runs`, поэтому `/app` отсутствовал в module search path.

После этого rollback отдельно не смог интерполировать Compose:

```text
HERMES_SANDBOX_GID is required
```

Systemd получает значение через `/srv/hermes-coders/launcher.env`, а direct
rollback Compose invocation этот env-file не передавал.

### Планируемый объём

- экспортировать `/app` как `PYTHONPATH` для обоих canonical coder services;
- передавать `launcher.env` direct rollback Compose invocation;
- добавить regression contracts для обеих production ошибок;
- не менять volumes, auth, ledger, workspaces, secrets или database state;
- слить только после зелёного required CI.

### Критерии готовности

- inline Python smoke импортирует bind-mounted `sandbox_launcher_client`;
- rollback Compose получает `HERMES_SANDBOX_GID` из canonical launcher env;
- release script проходит `bash -n`;
- required CI полностью зелёный;
- production acceptance выполняется только fresh exact-current-main release.

## После завершения

### Фактически сделано

- в окружение обоих coder services добавлен `PYTHONPATH=/app`;
- rollback Compose получает `--env-file /srv/hermes-coders/launcher.env`;
- добавлены regression tests для module path и rollback interpolation context;
- production persistent state не изменялся.

### Риски и ограничения

- production unit остаётся failed/disabled до fresh release;
- фактические canonical containers сейчас healthy, но coder и launcher symlink
  ещё отражают rollback state;
- workflow deploy user по-прежнему не имеет разрешённого non-interactive sudo;
- production acceptance ещё не выполнен.

### Миграции и совместимость

Миграций базы нет. Compose environment добавляет только `PYTHONPATH=/app` двум
coder services. Rollback CLI остаётся совместимым и теперь явно загружает
canonical launcher env. Persistent auth, data, volumes и secrets не меняются.

### Проверки

- `bash -n deploy/hermes-coders/release.sh`;
- exact string contract для двух `PYTHONPATH=/app` declarations;
- exact rollback `--env-file "$ROOT/launcher.env"` contract;
- полный required CI после открытия PR.

### PR и commit

- PR: `#651 Fix Hermes smoke imports and rollback environment`;
- ветка: `fix/hermes-smoke-rollback-env`;
- base: `76ce10d916e7901be6223534721e52adbd29dbe3`;
- итоговый head и merge commit фиксируются после required CI.

### Незавершённое

- дождаться required CI;
- выполнить squash merge;
- создать fresh release branch от нового current main;
- выполнить canonical release и подтвердить systemd, smoke и rollback contracts;
- удалить temporary compatibility files только после acceptance.

### Следующий шаг

Дождаться полного required CI, выполнить squash merge, создать fresh
exact-current-main release и повторить canonical production acceptance без
ручного изменения работающих containers.
