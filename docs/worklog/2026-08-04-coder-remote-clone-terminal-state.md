# Coder remote clone и terminal state

- Дата: 2026-08-04
- ID: CODER-REMOTE-CLONE-TERMINAL-STATE-20260804
- Линия/фаза: Hermes coder routing и workspace isolation
- Статус: частично
- Ветка: `fix/coder-remote-clone-terminal-state`
- Базовый commit: `f4f98ac2d57967a80f399b1986ad7cc069311c68`

## Перед началом

### Цель

Устранить падение per-run workspace preparation на partial/promisor checkout, гарантировать terminal failure вместо вечного `queued` и прекратить накопление zombie-процессов Git в coder-контейнерах.

### Исходный контекст

Read-only задача Velvet была принята central router с корректными `task_type=read_only`, `requested_tier=small`, `selected_primary_model=gpt-5.6-luna` и `mutation_policy=read_only`, но execution thread упал до запуска Codex:

```text
fatal: pack has 1 unresolved delta
fatal: fetch-pack: invalid index-pack output
```

`/workspace-base` является blobless promisor checkout:

```text
remote.origin.promisor=true
remote.origin.partialclonefilter=blob:none
```

A/B-проверка показала:

```text
local clone from /workspace-base, then fetch origin: exit 128
remote clone --filter=blob:none from origin: exit 0
```

Run остался в `queued`, потому что подготовка workspace выполнялась до terminal exception handling. Оба coder runner также работали как PID 1 без Docker init и накопили zombie-процессы `git`.

### Планируемый объём

- Перевести per-run checkout на direct remote partial clone.
- Не использовать `/workspace-base` как clone source.
- Переводить preparation errors в terminal `failed` с redacted диагностикой.
- Сохранять безопасный cleanup частичного workspace.
- Добавить Docker init для обоих coder services.
- Обновить runtime smoke и regression tests.
- Не выполнять production rollout в рамках PR.

### Критерии готовности

- Clone command использует `origin`, `--filter=blob:none`, `--single-branch` и validated default branch.
- Ошибка clone/checkout/snapshot не оставляет run в `queued`.
- Ledger получает `finished_at`, `error` и `workspace_preparation_failed`.
- `mutation_started=false` сохраняется для ошибки до execution.
- Compose включает init для coder runner.
- Smoke проверяет direct clone и отсутствие zombie.
- Focused и contract tests проходят на точном PR head.

### Риски и ограничения

- Direct clone требует доступности origin и корректного Git credential helper.
- Runtime smoke остаётся rollout-only, поскольку production restart не разрешён этим PR.
- Telegram automatic delegation bypass является отдельной границей и не исправляется этим change.
- Канонический nested bwrap rollout остаётся отдельным ранее подтверждённым blocker.

## После завершения

### Фактически сделано

- `_prepare_workspace()` клонирует напрямую из проверенного `origin`:
  - `--filter=blob:none`;
  - `--no-checkout`;
  - `--single-branch`;
  - `--branch <validated-default-branch>`.
- `/workspace-base` больше не передаётся в `git clone` как источник.
- Ошибка clone, checkout или baseline snapshot переводит run в terminal `failed`.
- Записываются `finished_at`, redacted `error`, `mutation_started=false` и `last_event.type=workspace_preparation_failed`.
- Частично подготовленный run workspace удаляется только внутри установленного workspace root.
- Codex runner services получили `init: true`.
- Runtime smoke использует direct remote clone и проверяет отсутствие zombie.
- Добавлены tests для promisor base, clone command и terminal preparation failure.

### Миграции и совместимость

- Миграции БД отсутствуют.
- API submit/status не меняется.
- Existing ledger, auth, codex-runs и workspace volumes не удаляются.
- Production checkout, контейнеры, systemd units, secrets и БД не изменялись.
- Deploy, restart, merge и rollback не выполнялись.

### Проверки

- A/B production diagnosis: local partial clone + fetch failed, direct remote partial clone succeeded.
- Exact Git clone syntax отдельно проверен на локальном bare remote.
- GitHub CI запускается на точном PR head.
- После merge обязательны `runtime_smoke.py`, `tier_provider_smoke.py`, `router_smoke.py` и read-only задачи Velvet/Max.

### PR и commit

- PR: #591.
- Ветка: `fix/coder-remote-clone-terminal-state`.
- Точный final head фиксируется после terminal CI и возможных review fixes.

### Незавершённое

- Terminal CI ещё должен подтвердить implementation.
- Production rollout не выполнен.
- Технический enforcement выбора `coderctl` Каэлем остаётся отдельной задачей.
- Nested bwrap architecture blocker не изменён этим PR.

### Следующий шаг

Дождаться terminal CI, исправить только подтверждённые blockers в этой же ветке и оставить PR draft до независимой проверки. После merge и отдельного разрешения выполнить controlled rollout на точный approved SHA, проверить отсутствие новых zombie и завершение small/read-only runs для Velvet и Max.
