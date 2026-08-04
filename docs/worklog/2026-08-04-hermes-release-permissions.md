# Сессия: права runtime sources в Hermes release

- Дата: `2026-08-04`
- ID: `hermes-release-permissions-20260804`
- Линия/фаза: `server operations / Hermes coder release`
- Статус: `частично`
- Ветка: `fix/hermes-release-worktree-permissions`
- Базовый commit: `d9a4d22ae03a1c974a70a6202d0acbb313eb7e27`
- Связанные PR и issue: `#620`, `#611`, `#616`, `#592`

## Перед началом

### Цель

Устранить fail-closed остановку Hermes coder production release, когда detached
Git worktree создаётся под `umask 077`, а bind-mounted runtime sources получают
режим `0600` и недоступны непривилегированному UID внутри контейнера.

### Исходный контекст

Production run `30947027911` успешно прошёл validation secrets, настройку SSH,
подключение к серверу, проверку exact current `main` и исходный container preflight.
Оба Hermes coder контейнера были `running`, `healthy`, с restart count `0` и
`init=true`. Release был остановлен `runtime_source_guard.py` до переключения на
новый runtime source, после чего fail-closed rollback пересоздал контейнеры из
предыдущего Compose source.

### Планируемый объём

- оставить remote shell и lock под строгим `umask 077`;
- разрешить чтение только allowlisted bind-mounted runtime source files;
- не добавлять group/world write или новые execute bits;
- сохранить отдельную fail-closed validation после исправления прав;
- покрыть изменение targeted unit tests;
- не менять bot, PostgreSQL, migrations, supervisor, router или sandbox policy.

### Критерии готовности

- runtime source с режимом `0600` получает только обязательный world-read bit;
- существующие owner execute bits сохраняются;
- отсутствующий runtime source по-прежнему завершает guard ошибкой;
- production release проходит source guard и все post-release checks;
- оба контейнера остаются healthy, restart count `0`, `init=true`;
- image IDs не меняются, mounted source SHA соответствует exact release commit;
- host и container zombie checks равны нулю;
- результат опубликован reporter workflow в issue `#592`.

## После завершения

### Фактически сделано

- `runtime_source_guard.py` сначала нормализует только `S_IROTH` для фиксированного
  списка runtime sources, затем выполняет прежнюю fail-closed validation;
- добавлены tests для режима `0600`, сохранения owner execute bit и missing source;
- SSH secrets, Compose security layers, images и deployment scope не изменены.

### Риски и ограничения

- изменение намеренно делает только allowlisted runtime files world-readable на
  production host, поскольку те же файлы должны читаться непривилегированным UID
  после bind mount;
- содержимое runtime sources является repository code, а не secret material;
- окончательное подтверждение зависит от повторного exact-current-main release.

### Миграции и совместимость

- database migrations отсутствуют;
- application bot stack не перезапускается;
- rollback contract и existing Compose security overlays сохраняются;
- изменение совместимо с уже созданным release worktree с режимами `0600`.

### Проверки

- targeted unit tests для runtime source guard;
- existing Hermes deploy workflow contract;
- required CI checks на exact PR head;
- после merge новый exact-main release ref и evidence comment в `#592`.

### PR и commit

- PR: `#620`;
- base: `d9a4d22ae03a1c974a70a6202d0acbb313eb7e27`;
- exact head фиксируется после обновления worklog и повторного CI;
- merge commit и production release ref фиксируются после зелёных required checks.

### Незавершённое

- дождаться required CI на обновлённом exact head;
- слить PR после зелёного результата;
- создать новый exact-current-main Hermes release ref;
- проверить production evidence и только затем закрыть rollout.

### Следующий шаг

Пройти CI, слить минимальный permission fix и повторить узкий Hermes coder release.
