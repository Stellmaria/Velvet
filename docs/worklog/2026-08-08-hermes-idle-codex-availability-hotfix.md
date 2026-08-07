# Hermes idle gate Codex availability hotfix

- Дата: 2026-08-08
- ID: hermes-idle-codex-availability-hotfix
- Линия/фаза: Hermes coder orchestration production reliability
- Статус: `завершено`
- Ветка: `hotfix/hermes-idle-ignore-codex-availability`
- Базовый commit: `07ba0676aa328afebe7d43cebaa36e75743f3c0b`

## Перед началом

### Цель

Устранить regression в Hermes sandbox idle gate, из-за которого persistent Codex availability state ошибочно классифицировался как активный coder run и навсегда блокировал canonical orchestration installer даже при отсутствии реальных активных задач.

### Исходный контекст

После восстановления ownership `/opt/data/tools` и `/opt/data/orchestration` production orchestration installer дошёл до sandbox idle gate и остановился с двумя записями вида `velvet:codex-availability:unknown` и `max:codex-availability:unknown`.

Кодовая проверка показала, что `ContextLauncherTierProviderManager` создаёт `CodexAvailabilityGate` с `root=self.store.root`. Поэтому state-файл `codex-availability.json` находится рядом с JSON run-ledgers каждого проекта. `deploy/hermes-coders/ensure_idle.py` перебирал все `*.json` в этих каталогах и интерпретировал любой объект без terminal `status` как активный run. Availability state не содержит run `status`, поэтому получал синтетический статус `unknown`.

### Планируемый объём

- Исключить из run-ledger scan ровно canonical state-файл `codex-availability.json`.
- Не ослаблять fail-closed поведение для любых других неожиданных, повреждённых или nonterminal run JSON.
- Добавить regression tests для Velvet и Max availability state.
- Проверить, что реальный nonterminal run продолжает блокировать rollout даже при наличии availability state.
- Не менять формат Codex availability, routing policy, secrets, production permissions или deployment semantics.

### Критерии готовности

- `codex-availability.json` не появляется в `active_ledger_runs()`.
- Реальный run со статусом `running` по-прежнему возвращается как active.
- Неизвестный повреждённый JSON по-прежнему приводит к `IdleError`.
- Protected CI проходит на final PR head.

### Риски и ограничения

- Исключение должно быть name-bound и не превращаться в широкое игнорирование state-like JSON.
- Production orchestration installer не запускается в рамках repo PR.
- Production update и typed Kael canary выполняются отдельно после merge при уже подтверждённом владельцем rollout scope.

## После завершения

### Фактически сделано

- В `deploy/hermes-coders/ensure_idle.py` добавлен фиксированный allowlist non-run state files, содержащий только `codex-availability.json`.
- `active_ledger_runs()` пропускает только этот canonical state-файл до run-ledger validation.
- Все остальные JSON продолжают проходить прежнюю strict validation.
- В `tests/test_hermes_launcher_security_helpers.py` добавлены regression tests для availability state обоих проектов и для coexistence с реальным `running` run.

### Миграции и совместимость

SQL migrations отсутствуют. Persistent availability state не переносится и не меняет формат. Существующие run-ledgers сохраняют прежнюю семантику и fail-closed validation.

### Проверки

- Кодовый root cause подтверждён связкой `CodexAvailabilityGate(root=self.store.root)` и glob `run_root.glob("*.json")` в idle gate.
- Regression tests добавлены в существующую Hermes launcher security helper suite.
- Protected GitHub CI должен подтвердить final integrated tree перед merge.

### PR и commit

- Ветка: `hotfix/hermes-idle-ignore-codex-availability`
- Base: `07ba0676aa328afebe7d43cebaa36e75743f3c0b`
- PR и merge commit фиксируются после успешных protected checks.

### Незавершённое

Production пока не обновлён до этого hotfix. После merge требуется один штатный Velvet update до актуального `main`, затем canonical `deploy/hermes-orchestration/install.sh`, ownership/idle verification и typed read-only Kael canary.

### Следующий шаг

Открыть PR, дождаться terminal success всех required checks, синхронизировать branch с актуальным `main` при необходимости и merge без обхода branch protection.
