# Сессия: production Server Supervisor update failure diagnostic

- Дата: `2026-08-07`
- ID: `server-supervisor-update-failure-diagnostic-20260807`
- Линия/фаза: `Velvet / production diagnostics`
- Статус: `частично`
- Ветка: `hotfix/hermes-coders-preserve-exec-modes-20260807`
- Базовый commit: `8282a8c0c6b7143caef8d8b26f4def7b55c4e9d6`

## Перед началом

### Цель

Получить bounded и redacted evidence из protected `server-supervisor.log` для failed production update operation `27e62156ffd1428d`, не расширяя права Каэля и не повторяя mutation вслепую.

### Исходный контекст

Production update через Server Supervisor завершился terminal `error` с публичным `error_code=runtimeerror` и сообщением `Operation failed. See protected Server Supervisor log.`

После ошибки подтверждено:

- production HEAD остался `0dceb104a8d5c6a1a25dda07c708b916f2e9439f`;
- fetched `origin/main` указывает на `8282a8c0c6b7143caef8d8b26f4def7b55c4e9d6`;
- checkout clean;
- Server Supervisor active/running;
- reconcile coders не запускался;
- `monitorctl incidents` не содержал целевого traceback/update failure.

Код Server Supervisor скрывает exception от operator API и пишет подробность в protected `server-supervisor.log`, поэтому текущего Kael read-only contour недостаточно для локализации failing command.

### Планируемый объём

- добавить отдельный production diagnostic workflow;
- использовать существующий production SSH environment;
- проверять ожидаемый production branch/HEAD/clean state;
- читать только `server-supervisor.log`;
- выбрать окно `2026-08-07 18:21:20-18:22:30 UTC` вокруг failed operation;
- вернуть максимум 100 строк;
- редактировать token/API-key/password/secret/credential-like значения;
- не выполнять update, restart, reconcile, Docker/systemd mutations или Git writes.

### Критерии готовности

- protected CI зелёный на exact PR head;
- merge-triggered diagnostic workflow завершён terminal;
- output содержит bounded redacted traceback/failing command либо явное `no_matching_log_lines=true`;
- production checkout не изменён диагностикой;
- evidence достаточно для отдельного минимального исправления или следующего диагностического шага без blind retry.

### Риски и ограничения

Workflow читает production log через privileged SSH contour, поэтому вывод должен быть bounded и redacted до публикации в Actions log. Диагностика привязана к конкретному старому production HEAD и временному окну failed operation; при неожиданном branch/HEAD/dirty state она должна fail closed. `.env.server` не печатается, из него читается только значение `VELVET_DATA_DIR` для вычисления log path.

## После завершения

### Фактически сделано

Добавлен `.github/workflows/production-server-supervisor-log-diagnostic.yml` с read-only production SSH diagnostic. Workflow проверяет expected production HEAD/clean state, вычисляет `server-supervisor.log`, собирает только заданное окно и публикует максимум 100 redacted строк.

### Миграции и совместимость

Миграций данных и runtime schema нет. Production application/runtime не изменяется diagnostic workflow. Workflow существует только как bounded observability bridge для конкретной failed operation.

### Проверки

Первый protected CI run подтвердил, что runtime/workflow checks стартуют, но `project notes contract` отклонил исходный worklog из-за отсутствия canonical разделов. Worklog приведён к canonical структуре; после этого требуется новый полный protected CI на новом exact head.

### PR и commit

PR #695 открыт против `main`. Ветка переиспользована после merged PR #694 из-за блокировки создания нового Git ref коннектором; сравнение с current `main` подтверждает, что diff PR #695 содержит ровно два новых файла: diagnostic workflow и этот worklog. Merge допустим только после terminal green protected CI на exact head.

### Следующий шаг

Дождаться protected CI, слить PR #695, затем прочитать merge-triggered production diagnostic output. По точной ошибке подготовить минимальный hotfix либо, если причина не попала в окно, скорректировать только diagnostic evidence contour. Production update до этого не повторять.

### Незавершённое

- дождаться нового protected CI на исправленном head;
- merge PR #695;
- разобрать merge-triggered production workflow output;
- локализовать exact failing stage/command;
- при необходимости подготовить отдельный hotfix;
- только после устранения причины повторить canonical production rollout.