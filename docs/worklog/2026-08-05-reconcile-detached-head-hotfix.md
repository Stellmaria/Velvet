# Сессия: hotfix reconcile для detached production checkout

- Дата: 2026-08-05
- ID: `reconcile-detached-head-hotfix-20260805`
- Линия/фаза: production infrastructure reconcile
- Статус: `завершено`
- Ветка: `fix/reconcile-safe-directory`
- Базовый commit: `224f34d31ea583319a6e25e32cdcf95c7a6a291f`
- Связанное issue: `#586`

## Перед началом

### Цель

Исправить production-сбой `reconcilectl.py submit librarian`, при котором root bridge сначала отклонял `/srv/velvet` из-за Git dubious ownership, а после точечного `safe.directory` оставался несовместим с штатным detached checkout, создаваемым Server Supervisor.

### Планируемый объём

- применять `safe.directory` только к точному production checkout;
- разрешить detached HEAD только при чистом дереве и полном совпадении `HEAD` с fetched `origin/main`;
- сохранить отказ для attached checkout на посторонней ветке;
- подключить проверенный entrypoint через systemd unit;
- установить entrypoint root-owned вне production checkout;
- добавить regression-тесты.

### Критерии готовности

- reconcile принимает штатный clean detached checkout на fetched `origin/main`;
- произвольный detached commit отклоняется;
- attached checkout не на `main` отклоняется;
- wildcard `safe.directory=*` не используется;
- root-сервис не исполняет код прямо из checkout пользователя `velvet`;
- required CI проходит.

## После завершения

### Фактически сделано

- добавлен `host_reconcile_entrypoint.py`, который загружает установленный allowlisted bridge и усиливает Git-проверку;
- все Git-команды bridge получают точный `-c safe.directory=/srv/velvet` через resolved app directory;
- detached checkout разрешён только при clean tree и `HEAD == refs/remotes/origin/main`;
- attached checkout на ветке, отличной от `main`, остаётся запрещён;
- installer размещает entrypoint root-owned в `/usr/local/libexec`;
- systemd unit переведён на установленный entrypoint, а не на код из checkout;
- добавлены regression-тесты для detached/attached сценариев и точного safe.directory.

### Проверки

- `python -m unittest tests.test_hermes_reconcile_checkout_entrypoint`;
- `python -m unittest tests.test_hermes_reconcile_contract`;
- полный required CI PR.

### Незавершённое

После merge требуется обновить production checkout, переустановить `deploy/hermes-reconcile/install.sh`, повторить `submit librarian`, дождаться terminal status и выполнить ручной smoke Storage #2168 при выключенном auto enqueue.
