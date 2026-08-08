# Launcher-visible workspace prompt fix

- Дата: 2026-08-08
- ID: `launcher-workspace-prompt`
- Линия/фаза: Hermes coder production smoke follow-up
- Статус: `завершено`
- Ветка: `fix/launcher-workspace-prompt`
- Базовый commit: `45ccf8121a055631bae9b660b38254a83ef60d98`

## Перед началом

### Цель

Исправить production read-only coder smoke, который корректно выбрал `byesu_provider`, но затем заблокировался до выполнения команды из-за неверного effective workspace path в prompt disposable sandbox.

### Подтверждённая причина

`AuditedTierProviderManager` создаёт per-run clone внутри coder controller container по пути `/opt/codex-runs/workspaces/<run_id>` и вставляет этот controller-visible path в system prompt. Host sandbox launcher затем bind-mount-ит тот же checkout в disposable container как `/workspace`, а sandbox entrypoint запускает Codex из `/workspace`.

В результате launcher-backed run получал инструкцию работать в `/opt/codex-runs/workspaces/<run_id>`, хотя внутри disposable sandbox существует только `/workspace`.

## После завершения

### Фактически сделано

- В `codex_launcher_runner.py` добавлена узкая трансляция только deterministic injected workspace notice.
- Controller/audit path и host workspace validation не меняются.
- В launcher prompt effective workspace становится `/workspace`.
- Запрет на `/workspace-base`, chat workspaces и sibling runs сохраняется.
- Произвольный user text с controller path не переписывается.
- Добавлен regression test для двух injected notice copies и отдельный test, что unrelated user text остаётся неизменным.

### Проверки

Repository CI должен подтвердить unit/contract checks на exact PR head. Production acceptance после merge выполняется повторением того же read-only smoke при `codex_available=false` с ожиданием `actual_route=byesu_provider`, terminal success без blocker и `mutation_started=false`.

### PR и commit

- Ветка: `fix/launcher-workspace-prompt`
- Base: `45ccf8121a055631bae9b660b38254a83ef60d98`
- PR и exact tested head фиксируются после открытия PR и полного required CI.

### Незавершённое

- До merge production остаётся на текущем launcher behavior.
- После merge требуется canonical `velvet update`, затем `deploy/hermes-orchestration/install.sh` без idle bypass.
- После rollout требуется повторить Smoke A и только после его успеха продолжить Telegram Kael canary.
