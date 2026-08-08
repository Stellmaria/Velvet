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

### Исходный контекст

После canonical production rollout Codex dynamic gate доказанно находился в `subscription_limit`: `codex_available=false`, `provider_available=false`, а recovery notification worker сохранил persistent active limit event. Production Smoke A корректно выбрал `byesu_provider` с `fallback_reason=subscription_cooldown` и не начал mutation, но задача завершилась `structured_output.status=blocked` до выполнения read-only команды.

`AuditedTierProviderManager` создаёт per-run clone внутри coder controller container по пути `/opt/codex-runs/workspaces/<run_id>` и вставляет этот controller-visible path в deterministic workspace notice. Host sandbox launcher проверяет тот же host checkout, затем bind-mount-ит его в disposable execution container как `/workspace`. Sandbox entrypoint запускает Codex из `/workspace`.

В результате launcher-backed run получал инструкцию работать в `/opt/codex-runs/workspaces/<run_id>`, хотя внутри disposable sandbox существует только `/workspace`.

### Планируемый объём

- Исправить только launcher-boundary представление effective workspace в injected prompt.
- Сохранить controller path `/opt/codex-runs/workspaces/<run_id>` для store, audit, host validation и launcher request contract.
- Сохранить запреты на `/workspace-base`, chat workspaces и sibling runs.
- Не переписывать произвольный пользовательский текст только из-за упоминания controller path.
- Добавить узкий regression test на обе копии injected workspace notice.
- Не менять Codex availability gate, Byesu routing, credentials, Telegram recovery worker или provider retry semantics.

### Критерии готовности

- Launcher-visible injected notice объявляет effective checkout как `/workspace`.
- Controller-visible path больше не присутствует в deterministic injected notice, передаваемом disposable sandbox.
- Host/controller workspace validation и persisted audit evidence остаются без изменений.
- Unrelated user text не подвергается path replacement.
- Required repository CI проходит на exact PR head.
- После merge и canonical rollout повторный production Smoke A завершается без blocker через `actual_route=byesu_provider` при `mutation_started=false`.

### Риски и ограничения

- Fix намеренно не меняет filesystem topology: `/workspace` является только sandbox-visible mount point, а controller/host path остаётся прежним.
- Нельзя заменять все вхождения `/opt/codex-runs/...` в произвольном prompt, иначе диагностический user text мог бы быть искажён.
- Repository tests не заменяют production acceptance, потому что реальный launcher socket, host bind mount и Byesu route проверяются только после canonical rollout.
- До merge production остаётся на текущем behavior; ручной patch server runtime не используется.

## После завершения

### Фактически сделано

- В `codex_launcher_runner.py` добавлена узкая трансляция только deterministic injected workspace notice.
- Controller/audit path и host workspace validation не меняются.
- В launcher prompt effective workspace становится `/workspace`.
- Запрет на `/workspace-base`, chat workspaces и sibling runs сохраняется.
- Произвольный user text с controller path не переписывается.
- Добавлен regression test для двух injected notice copies и отдельный test, что unrelated user text остаётся неизменным.

### Изменённые модули и контракты

- `deploy/hermes-coders/codex_launcher_runner.py`: launcher-boundary prompt translation.
- `tests/test_hermes_launcher_workspace_prompt.py`: regression coverage.
- `docs/worklog/2026-08-08-launcher-workspace-prompt.md`: rollout evidence и acceptance contract.

Launcher request schema, host workspace path, Docker bind source, sandbox mount `/workspace`, dynamic availability state и Telegram recovery state format не меняются.

### Миграции и совместимость

SQL migrations, environment migrations и persistent-state migrations отсутствуют. Existing launcher protocol остаётся совместимым: controller по-прежнему передаёт workspace `/opt/codex-runs/workspaces/<run_id>`, host launcher по-прежнему валидирует соответствующий checkout и монтирует его как `/workspace`. Изменяется только текст deterministic workspace notice, видимый модели внутри disposable sandbox.

### Проверки

- Production evidence до fix: `actual_route=byesu_provider`, `fallback_reason=subscription_cooldown`, `mutation_started=false`, но `structured_output.status=blocked` из-за попытки использовать controller-only path.
- Regression test проверяет перевод обеих injected notice copies в `/workspace`.
- Regression test проверяет отсутствие broad replacement в unrelated user text.
- Protected CI запускается заново на каждом новом exact head; старый green после изменения head не переиспользуется.
- Production acceptance после merge выполняется повторением того же read-only smoke при `codex_available=false` с ожиданием `actual_route=byesu_provider`, terminal success без blocker и `mutation_started=false`.

### PR и commit

- Ветка: `fix/launcher-workspace-prompt`
- Base: `45ccf8121a055631bae9b660b38254a83ef60d98`
- PR: `#730`
- Exact tested head фиксируется после этого worklog-contract fix и полного required CI.
- Merge разрешён только для exact green head при актуальном `behind_by=0` относительно `main`.

### Незавершённое

- До merge production остаётся на текущем launcher behavior.
- После merge требуется canonical `velvet update`, clean checkout и `deploy/hermes-orchestration/install.sh` без idle bypass.
- После rollout требуется повторить Smoke A и только после его успеха продолжить Telegram Kael canary.
- Пятичасовой Codex availability watcher и последующий real recovery notification остаются отдельными rollout checks и этим fix не изменяются.

### Следующий шаг

Дождаться terminal success всех required workflows на новом exact PR head, повторно проверить current `main` и `behind_by=0`, затем merge только exact tested head. После merge обновить production исключительно canonical update/orchestration path и повторить read-only Smoke A с теми же acceptance criteria.
