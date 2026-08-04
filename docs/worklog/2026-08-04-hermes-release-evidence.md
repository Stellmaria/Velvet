# Сессия: наблюдаемое подтверждение Hermes release

- Дата: `2026-08-04`
- ID: `hermes-release-evidence-20260804`
- Линия/фаза: `server operations / release observability`
- Статус: `частично`
- Ветка: `ops/hermes-release-evidence`
- Базовый commit: `2827fb7aba72c0447f16ddf05383745a9276e9bd`
- Связанные PR и issue: `#611`, `#597`, `#592`

## Перед началом

### Цель

Сделать результат push-triggered production release доступным как проверяемое
GitHub evidence без SSH-команд пользователя и без расширения production scope.

### Исходный контекст

Изолированный workflow Hermes coder уже создаёт detached worktree, пересоздаёт
только два coder-контейнера и выполняет health, source SHA, image identity, init и
zombie checks. Используемый коннектор показывает только pull-request-triggered
Actions runs, поэтому создание release ref само по себе не даёт наблюдаемого итога
операции. Делать вывод «ветка создана, значит deploy успешен» недопустимо.

### Планируемый объём

- добавить reporter на событие `workflow_run` завершённого Hermes release;
- не checkout-ить и не исполнять код release branch;
- валидировать exact SHA, встроенный в release ref;
- читать только завершённый Actions log;
- редактировать credential-like значения и ограничивать размер excerpt;
- публиковать outcome и verification tail в фиксированный issue `#592`;
- оставлять reporter failed, если production release завершился неуспешно.

### Критерии готовности

- reporter запускается только после завершения `deploy Hermes coders`;
- release ref и workflow head SHA совпадают;
- workflow не checkout-ит и не исполняет release code;
- permissions ограничены чтением Actions/code и записью комментария issue;
- credential-like значения редактируются, excerpt ограничен 80 строками;
- issue `#592` получает outcome, commit, ref, run URL и verification tail;
- failed release документируется и оставляет reporter workflow красным;
- повторный exact-main release подтверждён evidence comment с outcome `success`.

## После завершения

### Фактически сделано

- добавлен `.github/workflows/report-hermes-coder-release.yml`;
- reporter запускается только после завершения workflow `deploy Hermes coders`;
- push release ref обязан иметь вид `release/hermes-coders-<40-char SHA>` и
  совпадать с `workflow_run.head_sha`;
- reporter использует только `actions: read`, `contents: read`, `issues: write`;
- release log читается через `gh run view`, credential-like значения редактируются,
  а в issue попадают только последние 80 строк;
- комментарий в `#592` содержит conclusion, commit, ref, event, run URL и run ID;
- failed release сначала документируется, затем reporter завершается ошибкой;
- добавлен contract test, запрещающий checkout, SSH, Docker и write-доступ к code.

### Риски и ограничения

- комментарий зависит от доступности GitHub Issues API;
- редактирование является дополнительной защитой, а не заменой стандартного
  GitHub secret masking;
- reporter подтверждает данные release log, но не выполняет независимое повторное
  подключение к production;
- issue `#592` остаётся постоянным журналом этого operational rollout;
- первый release ref, созданный до появления reporter, не имеет evidence comment и
  не считается подтверждённым завершением.

### Миграции и совместимость

- application, database и migrations не изменяются;
- reporter не подключается к production и не управляет контейнерами;
- исходный fail-closed rollback workflow не меняется;
- permissions не включают `contents: write` или `actions: write`;
- production release по-прежнему затрагивает только два Hermes coder containers.

### Проверки

- targeted workflow contracts должны пройти в selective CI;
- ShellCheck и CodeQL Actions должны проверить новый workflow;
- Docker required contexts создаются через обновлённый Hermes release runbook;
- после merge создаётся новый exact-main release ref;
- успешное завершение принимается только после появления evidence comment в
  issue `#592` с outcome `success` и серверным verification tail.

### PR и commit

- PR создаётся из `ops/hermes-release-evidence` после проверки четырёхфайлового
  diff;
- окончательные PR, merge SHA, release ref и evidence comment фиксируются после
  зелёного exact-head CI.

### Незавершённое

- открыть и слить PR reporter workflow;
- создать новый exact-current-main release ref;
- дождаться комментария GitHub Actions в issue `#592`;
- проверить в evidence tail health, restart count, init, mounted source SHA и
  отсутствие zombies;
- только после этого считать production rollout завершённым.

### Следующий шаг

Пройти required checks, слить reporter workflow и повторить узкий Hermes release
на новом exact `main`, получив аудируемый outcome в issue `#592`.
