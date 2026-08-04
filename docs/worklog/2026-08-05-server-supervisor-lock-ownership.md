# Сессия: ownership hotfix deploy-lock Server Supervisor

- Дата: 2026-08-05
- ID: `server-supervisor-lock-ownership-20260805`
- Линия/фаза: production server operations
- Статус: `завершено`
- Ветка: `fix/server-supervisor-lock-ownership`
- Базовый commit: `f875062956c707b81e3a2e3b095c0c80c5cd442a`
- Связанное issue: `#586`

## Перед началом

### Цель

Устранить production-сбой Server Supervisor update, при котором непривилегированный runtime `velvet` не мог открыть `/tmp/velvet-deploy.lock`, оставленный владельцем root.

### Исходный контекст

Production bot оставался healthy на предыдущем commit. Update завершался до fetch, backup и Docker с `Permission denied` на строке открытия общего deploy-lock. Systemd unit корректно запускает Supervisor как `velvet`, а ручной installer и некоторые SSH-операции выполняются от root.

### Планируемый объём

- сохранить единый lock для Supervisor и ручных server operations;
- сериализовать installer с активным deploy через тот же `flock`;
- безопасно нормализовать owner и mode lock-файла;
- отклонять неожиданный не-regular lock path;
- добавить regression-тест.

### Критерии готовности

- installer от root открывает общий lock и отказывается работать при занятом lock;
- после installer файл принадлежит `velvet:velvet` и имеет mode `0600`;
- wildcard permissions и world-writable lock не используются;
- required CI проходит.

### Риски и ограничения

Installer должен запускаться от root, как и раньше. Исправление не удаляет lock без проверки и не обходит `flock`. Если path заменён директорией, symlink или иным неожиданным объектом, installer завершается с ошибкой.

## После завершения

### Фактически сделано

- installer использует тот же `/tmp/velvet-deploy.lock` и удерживает его на отдельном file descriptor;
- active deploy блокирует installer с exit code 75;
- regular lock нормализуется в `velvet:velvet` и `0600`;
- добавлен отдельный regression contract.

### Миграции и совместимость

SQL-миграций нет. Docker Compose и application runtime не меняются. Существующий lock path сохранён, поэтому ручной deploy и Server Supervisor продолжают сериализоваться между собой.

### Проверки

- `python -m unittest tests.test_server_supervisor_lock_installer`;
- shell syntax и ShellCheck installer;
- полный required CI PR.

### PR и commit

PR создаётся из `fix/server-supervisor-lock-ownership` в `main`.

### Незавершённое

После merge требуется обновить production, запустить installer один раз и повторить Server Supervisor update. Текущий production lock до merge ремонтируется отдельной guarded-командой только при отсутствии holder.

### Следующий шаг

Открыть PR, дождаться зелёных checks и слить hotfix.
