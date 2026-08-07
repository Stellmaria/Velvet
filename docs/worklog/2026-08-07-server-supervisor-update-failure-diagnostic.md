# Сессия: production Server Supervisor update failure diagnostic

- Дата: `2026-08-07`
- ID: `server-supervisor-update-failure-diagnostic-20260807`
- Линия/фаза: `Velvet / production diagnostics`
- Статус: `частично`
- Базовый production commit: `0dceb104a8d5c6a1a25dda07c708b916f2e9439f`
- Целевой main commit на момент диагностики: `8282a8c0c6b7143caef8d8b26f4def7b55c4e9d6`
- Failed operation: `27e62156ffd1428d`

## Перед изменением

Production update через Server Supervisor завершился terminal `error` с публичным `error_code=runtimeerror` и сообщением `Operation failed. See protected Server Supervisor log.`

После ошибки подтверждено:

- production HEAD остался `0dceb104a8d5c6a1a25dda07c708b916f2e9439f`;
- fetched `origin/main` указывает на `8282a8c0c6b7143caef8d8b26f4def7b55c4e9d6`;
- checkout clean;
- Server Supervisor active/running;
- reconcile coders не запускался;
- `monitorctl incidents` не содержал целевого traceback/update failure.

Код Server Supervisor намеренно скрывает exception от operator API и пишет подробность в protected `server-supervisor.log`, поэтому текущего Kael read-only contour недостаточно для локализации failing command.

## Что сделано

Добавлен отдельный production diagnostic workflow `.github/workflows/production-server-supervisor-log-diagnostic.yml`.

Workflow:

- запускается только при merge изменения собственного файла в `main`;
- использует существующий production SSH environment;
- не выполняет update, restart, reconcile, Docker/systemd mutations или Git writes;
- проверяет, что production checkout находится на ожидаемом старом HEAD и clean;
- читает только `server-supervisor.log`;
- выбирает bounded окно `2026-08-07 18:21:20-18:22:30 UTC` вокруг operation `27e62156ffd1428d`;
- возвращает максимум 100 строк;
- редактирует token/API-key/password/secret/credential-like значения;
- не печатает `.env.server` и использует из него только `VELVET_DATA_DIR` для вычисления log path.

## Ограничения безопасности

- Лог читается read-only.
- Содержимое файлов приложения и secrets не запрашивается.
- Вывод bounded и redacted до публикации в Actions log.
- Workflow fail-closed при неожиданном production branch/HEAD/dirty state или отсутствии ожидаемого regular log file.

## Проверка

До merge требуется protected CI на exact PR head.

После merge acceptance:

1. merge-triggered diagnostic workflow завершён terminal;
2. output содержит либо bounded redacted traceback/failing command, либо явное `no_matching_log_lines=true`;
3. production checkout не изменён диагностикой;
4. причина failed update используется для отдельного минимального исправления, без blind retry.

## Решения

- Не повторять `velvet update` до получения protected error evidence.
- Не расширять права Каэля прямым filesystem/journal доступом ради одноразовой диагностики.
- Использовать production Actions contour с минимальным read-only scope и redaction.

### Незавершённое

- Получить protected CI green и слить diagnostic PR.
- Разобрать merge-triggered production workflow output.
- Локализовать exact failing stage/command.
- При необходимости подготовить отдельный hotfix и только после него повторить canonical production rollout.