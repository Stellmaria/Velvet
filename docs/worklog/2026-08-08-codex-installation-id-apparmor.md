# Сессия: Codex installation identity AppArmor write scope

- Дата: `2026-08-08`
- ID: `codex-installation-id-apparmor-20260808`
- Линия/фаза: `Velvet / Hermes Codex availability production rollout`
- Статус: `частично`
- Ветка: `fix/codex-installation-id-apparmor`
- Базовый commit: `cee19bc5ce07cbaa96504102ab28c029cfcff7b4`

## Перед началом

### Цель

Разрешить Codex CLI 0.144.1 сохранять локальный `CODEX_HOME/installation_id`, не делая весь `/opt/codex` writable и не ослабляя read-only boundary для auth/config state.

### Исходный контекст

После переноса SQLite state в `CODEX_SQLITE_HOME=/opt/codex-runs/sqlite` production availability probe перестал падать на SQLite initialization, но оба проекта всё ещё возвращали `provider_available=null`, `reason=unknown` и `Permission denied (os error 13)`.

Production diagnostics подтвердили:

- `/srv/hermes-coders/codex-runs/{velvet,max}` принадлежат UID/GID `10000:10000`;
- coder runtime также работает как UID/GID `10000:10000`;
- создание и удаление файла в `/opt/codex-runs/sqlite` проходит (`WRITE_OK`);
- AppArmor разрешает `/opt/codex-runs/** rwk`;
- kernel audit фиксирует `DENIED` только для создания `/opt/codex/.tmp*` и открытия `/opt/codex/installation_id` с write/create;
- upstream Codex `resolve_installation_id()` открывает `installation_id` как read/write/create и использует file locking, поэтому заранее существующего read-only UUID недостаточно.

### Планируемый объём

- сохранить `/opt/codex/**` read-only по умолчанию;
- разрешить `rwk` только для `/opt/codex/installation_id`;
- разрешить `rwk` только для same-directory временных `/opt/codex/.tmp*`, используемых pinned CLI при атомарном сохранении identity;
- зафиксировать regression assertions, запрещающие broad writable `/opt/codex/**`;
- не менять auth.json, config.toml, SQLite home, provider routing или credential model.

### Критерии готовности

- protected CI green на exact PR head;
- AppArmor contract явно разрешает только installation identity paths;
- broad write rule для `/opt/codex/**` отсутствует;
- после production reconcile `codex_availability_ctl.py refresh` больше не получает AppArmor `Permission denied` на `installation_id`;
- availability state становится фактическим `available` либо `subscription_limit`, а не `unknown` из-за local filesystem boundary.

### Риски и ограничения

`installation_id` является локальной machine identity Codex и upstream требует write/create/lock даже при существующем валидном UUID. Разрешение шире двух конкретных path нарушило бы существующую read-only границу credential/config home, поэтому hotfix намеренно не расширяет права на другие файлы `/opt/codex`.

## После завершения

### Фактически сделано

- в `apparmor-hermes-codex-runner` добавлены narrow `rwk` rules для `/opt/codex/installation_id` и `/opt/codex/.tmp*`;
- общий `/opt/codex/** r` сохранён;
- contract test дополнен positive assertions для двух identity paths и negative assertion против broad `/opt/codex/** rw`.

### Миграции и совместимость

Миграций данных нет. `CODEX_SQLITE_HOME=/opt/codex-runs/sqlite` остаётся без изменений. Существующие auth/config state и project isolation не меняются.

### Проверки

PR #715 открыт. До merge требуется полный protected CI на exact PR head. После merge требуется production update, canonical Hermes orchestration reconcile и live `codex_availability_ctl.py refresh` для Velvet и Max.

### PR и commit

PR #715 — `Fix Codex installation identity AppArmor writes`. Текущий head после фиксации worklog определяется GitHub. Merge допустим только после terminal green protected CI на exact head и проверки, что ветка не отстала от актуального `main`.

### Следующий шаг

Дождаться required CI PR #715, слить exact tested head, затем развернуть через canonical production update/reconcile и проверить отсутствие новых AppArmor denial на `installation_id`.

### Незавершённое

- получить полный green protected CI;
- merge exact tested head;
- production rollout и live availability refresh;
- отдельно исправить устаревший server preflight contract для server-side Krita.
