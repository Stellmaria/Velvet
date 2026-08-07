# Сессия: Server Supervisor update e06bcb64 diagnostic

- Дата: `2026-08-07`
- ID: `server-supervisor-e06bcb64-diagnostic-20260807`
- Линия/фаза: `Velvet / production diagnostics`
- Статус: `частично`
- Production HEAD после rollback: `0dceb104a8d5c6a1a25dda07c708b916f2e9439f`
- Целевой main commit: `056242d2ffdb3b8696d6d78c8f975459acba077d`
- Failed operation: `e06bcb64c2764cba`

## Перед изменением

После merge PR #696 повторный owner-authorized `velvet update` дошёл до целевого checkout и перевёл bot через `starting`, но завершился terminal `error`:

- `started_at=2026-08-07T18:52:57.211586+00:00`;
- `completed_at=2026-08-07T18:54:34.563466+00:00`;
- `error_code=runtimeerror`;
- публичный operator API сообщает только `Operation failed. See protected Server Supervisor log.`

После ошибки production checkout снова находится на `0dceb104a8d5c6a1a25dda07c708b916f2e9439f`, `remote_head_sha=056242d2ffdb3b8696d6d78c8f975459acba077d`, `dirty=false`.

Предыдущий подтверждённый blocker `build tag cannot contain a digest` исправлен PR #696, поэтому новый terminal error требует отдельного evidence из protected Server Supervisor log, без blind retry.

## Что сделано

Обновлён `.github/workflows/production-server-supervisor-log-diagnostic.yml` для bounded read-only диагностики operation `e06bcb64c2764cba`.

Workflow после merge:

- проверяет production branch `main`, ожидаемый rollback HEAD `0dceb104...` и clean tracked checkout;
- читает только `server-supervisor.log`;
- ограничивает поиск окном `2026-08-07 18:52:50-18:54:45 UTC`;
- предпочитает exact log record с marker `Server Supervisor operation failed kind=update`;
- если marker не найден, использует bounded fallback window;
- возвращает максимум 180 строк;
- redacts authorization bearer, API key, token, password, secret, credential, PostgreSQL credentials и распространённые token formats;
- не выполняет update, rollback, restart, reconcile, Docker/systemd mutations или Git writes на production.

## Acceptance

1. protected PR CI green на exact head;
2. merge-triggered diagnostic workflow terminal;
3. output содержит exact failure record/traceback либо явный bounded fallback/no-match;
4. production checkout остаётся неизменным;
5. следующий hotfix строится только по полученному failure evidence.

## Решения

- Не повторять `velvet update`, пока operation `e06bcb64c2764cba` не локализована по protected log.
- Не запускать `reconcile coders` до terminal успешного production update на exact target SHA.
- Не расширять постоянные права Каэля ради чтения protected host log, если достаточно одноразового GitHub Actions diagnostic contour.

### Незавершённое

- дождаться protected CI;
- merge diagnostic PR;
- разобрать merge-triggered protected output;
- локализовать exact failing command/stage;
- при необходимости подготовить минимальный hotfix и canonical rollout.