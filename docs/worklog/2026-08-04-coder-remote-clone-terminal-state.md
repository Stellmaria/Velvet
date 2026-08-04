# Coder remote clone и terminal state

- Дата: 2026-08-04
- Ветка: `fix/coder-remote-clone-terminal-state`
- База: `f4f98ac2d57967a80f399b1986ad7cc069311c68`
- Статус: implementation prepared, production rollout not performed

## Инцидент

Read-only задача Velvet была принята central router и получила корректные поля:

- `task_type=read_only`;
- `requested_tier=small`;
- `selected_primary_model=gpt-5.6-luna`;
- `mutation_policy=read_only`.

Execution thread упал до запуска Codex:

```text
fatal: pack has 1 unresolved delta
fatal: fetch-pack: invalid index-pack output
```

Run остался в `queued`, потому что подготовка workspace выполнялась до terminal exception handling.

## Воспроизведение

`/workspace-base` является blobless promisor checkout:

```text
remote.origin.promisor=true
remote.origin.partialclonefilter=blob:none
```

A/B-проверка:

```text
local clone from /workspace-base, then fetch origin: exit 128
remote clone --filter=blob:none from origin: exit 0
```

Также оба coder runner работали как PID 1 без Docker init и накопили zombie-процессы `git`.

## Изменения

1. Per-run workspace клонируется напрямую из проверенного `origin`:
   - `--filter=blob:none`;
   - `--no-checkout`;
   - `--single-branch`;
   - `--branch <validated-default-branch>`.
2. `/workspace-base` больше не используется как clone source.
3. Ошибка clone, checkout или baseline snapshot переводит run в terminal `failed`:
   - `finished_at`;
   - redacted `error`;
   - `last_event.type=workspace_preparation_failed`;
   - `mutation_started=false`.
4. Частично подготовленный run workspace удаляется в ограниченном каталоге run.
5. Codex runner services получают `init: true` для reaping дочерних процессов.
6. Runtime smoke использует тот же direct remote clone contract и проверяет отсутствие zombie.
7. Regression tests проверяют promisor base, remote clone command и отсутствие вечного `queued`.

## Границы

- Production checkout, контейнеры, systemd units, secrets и базы данных не изменялись.
- Deploy, restart, merge и rollback не выполнялись.
- Telegram automatic delegation bypass является отдельной границей: этот change исправляет central coder execution после корректного submit, но не заменяет технический enforcement выбора `coderctl` в основном Hermes.

## Rollout-only проверки

После merge и отдельного разрешения:

1. обновить production checkout на точный approved SHA;
2. пересобрать coder images через канонический installer;
3. перезапустить только coder lifecycle штатным systemd unit;
4. выполнить `runtime_smoke.py`, `tier_provider_smoke.py`, `router_smoke.py`;
5. отправить по одной small/read-only задаче Velvet и Max;
6. проверить terminal ledger fields и отсутствие новых zombie;
7. не удалять ledger, auth, codex-runs или workspace volumes.