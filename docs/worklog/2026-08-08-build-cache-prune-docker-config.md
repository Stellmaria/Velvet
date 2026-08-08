# Build cache prune: dedicated Docker config follow-up

- Дата: 2026-08-08
- ID: `2026-08-08-build-cache-prune-docker-config`
- Линия/фаза: server operations / housekeeping follow-up
- Статус: `завершено`
- Ветка: `fix/build-cache-prune-docker-config`

## Перед началом

### Цель

Укрепить только что добавленный weekly BuildKit prune перед production rollout: maintenance service должен использовать тот же dedicated writable Docker config, что и штатный deploy/Supervisor, а не зависеть от `~/.docker` при `ProtectHome=true`.

### Исходный контекст

PR #728 добавил безопасный weekly `docker builder prune`, общий deploy lock и systemd sandbox. При финальной pre-production проверке обнаружено, что service не задавал `DOCKER_CONFIG`, хотя `ProtectHome=true` закрывает доступ к home и исторически именно запись Docker/buildx metadata в home была причиной принудительного legacy builder режима.

### Планируемый объём

- задать `DOCKER_CONFIG=/srv/velvet/data/runtime/docker-config` в prune service;
- разрешить запись только в этот Docker config и `/tmp` внутри `ProtectSystem=strict`;
- installer должен создать directory с owner `velvet:velvet` и mode `0700`;
- обновить regression contract.

### Критерии готовности

- prune service не зависит от `/home/velvet/.docker`;
- Docker config directory подготовлен до enable timer;
- sandbox сохраняет минимальный writable surface;
- tests, ShellCheck и required CI зелёные.

### Риски и ограничения

Изменение не расширяет набор очищаемых Docker объектов: команда остаётся только `docker builder prune -af --filter until=168h`. Runtime containers, images, volumes и model data этим follow-up не затрагиваются.

## После завершения

### Фактически сделано

`velvet-build-cache-prune.service` теперь задаёт dedicated `DOCKER_CONFIG` и разрешает запись только в `/srv/velvet/data/runtime/docker-config` плюс общий `/tmp` для deploy lock.

Installer создаёт Docker config directory как `velvet:velvet` с mode `0700` перед установкой и enable timer.

### Изменённые модули и контракты

- `deploy/systemd/velvet-build-cache-prune.service`;
- `deploy/server/install-build-cache-prune.sh`;
- `tests/test_server_housekeeping_contract.py`.

### Миграции и совместимость

SQL-миграций нет. Schedule, prune age, deploy lock и prune command не изменялись.

### Проверки

Regression contract проверяет explicit `DOCKER_CONFIG`, writable sandbox path, создание каталога installer-ом и сохранение unprivileged service model.

### PR и commit

Follow-up PR создаётся и сливается только после полного required CI.

### Незавершённое

После merge остаётся только production rollout housekeeping changes, установка timer и host Ubuntu package updates.

### Следующий шаг

Открыть follow-up PR, дождаться required CI, слить в `main`, затем обновить VPS штатным deploy и применить host maintenance.
