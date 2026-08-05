# Сессия: repair legacy backup permissions

- Дата: 2026-08-05
- ID: `2026-08-05-legacy-backup-permission-repair`
- Линия/фаза: hotfix / server deployment reliability
- Статус: `в работе`
- Ветка: `fix/legacy-backup-permissions`
- Базовый commit: `503bf696a4b723b733f8835dcc93cb5c122a7c3e`

## Перед началом

### Цель

Сделать существующие PostgreSQL dump-файлы в server backup directory читаемыми для bot container до запуска Telegram Storage Migration, а не исправлять каждый старый файл вручную после очередного `PermissionError`.

### Исходный контекст

PR #643 изолировал ошибку одного нечитаемого dump внутри Telegram Storage Migration. Однако legacy-файл `/app/backups/pre-z032-20260804T183304Z-ca860bdf038c.dump` остаётся с host-level правами, которые не позволяют container UID прочитать его.

Текущий deploy создаёт новый predeploy dump при `umask 077`, затем явно устанавливает ему mode `0644`. Старые `*.dump` и `*.dump.json`, созданные прежними deployment/migration путями, не нормализуются. Поэтому кодовая изоляция предотвращает fatal-остановку, но operational debt сохраняется.

### Планируемый объём

- добавить в `deploy/server/deploy.sh` идемпотентную нормализацию mode `0644` для top-level regular `*.dump` и `*.dump.json`;
- запускать repair до early exit `Velvet is already at ...`, чтобы повторный deploy мог исправить legacy-файлы без смены revision;
- не переходить по symlink и не обходить вложенные каталоги;
- при невозможности изменить mode завершать deploy до code reset и запуска сервисов;
- расширить server deployment contract test.

### Критерии готовности

- legacy dump с mode `0600`, принадлежащий deploy-пользователю, становится читаемым bot container;
- manifest получает тот же contract;
- symlink и вложенные файлы не затрагиваются;
- repair выполняется даже при отсутствии нового target SHA;
- `bash -n`, deployment contract и обязательные CI checks проходят;
- PR слит только с неизменившимся проверенным head.

### Риски и ограничения

Deploy-пользователь не может исправить файл, принадлежащий другому UID без соответствующих host permissions. В этом случае deploy обязан остановиться с точным путём, а не продолжать с заведомо нечитаемым backup. Mode `0644` уже является действующим contract для новых predeploy dump; изменение распространяет его на legacy artifacts и не расширяет область за пределы private backup directory.

## После завершения

Будет заполнено после проверки и merge.
