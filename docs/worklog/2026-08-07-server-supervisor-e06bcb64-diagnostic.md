# Сессия: Server Supervisor update e06bcb64 diagnostic

- Дата: `2026-08-07`
- ID: `server-supervisor-e06bcb64-diagnostic-20260807`
- Линия/фаза: `Velvet / production diagnostics`
- Статус: `частично`
- Ветка: `diag/server-supervisor-e06bcb64-20260807`
- Базовый commit: `056242d2ffdb3b8696d6d78c8f975459acba077d`
- Production HEAD после rollback: `0dceb104a8d5c6a1a25dda07c708b916f2e9439f`
- Failed operation: `e06bcb64c2764cba`

## Перед началом

### Цель

Получить bounded redacted evidence из protected `server-supervisor.log` для failed production update operation `e06bcb64c2764cba`, локализовать exact failing command/stage и исключить blind retry.

### Исходный контекст

После merge PR #696 повторный owner-authorized `velvet update` дошёл до целевого checkout и перевёл bot через `starting`, но завершился terminal `error`:

- `started_at=2026-08-07T18:52:57.211586+00:00`;
- `completed_at=2026-08-07T18:54:34.563466+00:00`;
- `error_code=runtimeerror`;
- публичный operator API сообщает только `Operation failed. See protected Server Supervisor log.`

После ошибки production checkout снова находится на `0dceb104a8d5c6a1a25dda07c708b916f2e9439f`, `remote_head_sha=056242d2ffdb3b8696d6d78c8f975459acba077d`, `dirty=false`.

Предыдущий blocker `build tag cannot contain a digest` уже исправлен PR #696, поэтому этот terminal error рассматривается как отдельная причина.

### Планируемый объём

- retarget существующего read-only production diagnostic workflow на окно `2026-08-07 18:52:50-18:54:45 UTC`;
- предпочитать exact log record с marker `Server Supervisor operation failed kind=update`;
- использовать bounded fallback window только если marker не найден;
- возвращать максимум 180 строк после redaction;
- проверять production branch `main`, expected rollback HEAD `0dceb104...` и clean tracked checkout;
- не выполнять update, rollback, restart, reconcile, Docker/systemd mutations или Git writes на production.

### Критерии готовности

- protected PR CI green на exact head;
- merge-triggered diagnostic workflow terminal;
- output содержит exact failure record/traceback либо явный bounded fallback/no-match;
- production checkout остаётся неизменным;
- следующий hotfix строится только по полученному failure evidence.

### Риски и ограничения

Workflow получает read-only SSH доступ к production log contour, поэтому output должен оставаться bounded и redacted. Диагностика не должна менять production state и не должна превращаться в постоянный обход Kael permission model.

## После завершения

### Фактически сделано

- `.github/workflows/production-server-supervisor-log-diagnostic.yml` retargeted на operation `e06bcb64c2764cba`;
- добавлен exact failure-record marker filter;
- добавлен bounded fallback window;
- redaction расширен на credential-like assignments;
- production expected HEAD сохранён на подтверждённом rollback commit `0dceb104...`.

### Миграции и совместимость

Миграций данных и runtime config нет. Production services, `.env.server`, checkout и Docker/systemd state workflow не изменяет.

### Проверки

До merge требуется полный protected CI. После merge требуется terminal success diagnostic workflow и разбор redacted evidence.

### PR и commit

PR #697. Exact PR head после правки worklog определяется GitHub и merge допускается только после terminal green protected CI.

### Следующий шаг

После merge получить protected Server Supervisor failure record для `e06bcb64c2764cba`, определить exact failing command/stage и подготовить минимальный отдельный hotfix, если он требуется.

### Незавершённое

- дождаться protected CI;
- merge diagnostic PR;
- разобрать merge-triggered protected output;
- локализовать exact failing command/stage;
- при необходимости подготовить минимальный hotfix и canonical rollout.