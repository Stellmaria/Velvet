# Сессия: repair legacy backup permissions

- Дата: 2026-08-05
- ID: `2026-08-05-legacy-backup-permission-repair`
- Линия/фаза: hotfix / server deployment reliability
- Статус: `завершено`
- Ветка: `fix/legacy-backup-permissions`
- Базовый commit: `503bf696a4b723b733f8835dcc93cb5c122a7c3e`
- Проверенный production head: `af37e860b34b1b991a94c0a5852d8e5381adb915`

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

### Фактически сделано

В `deploy/server/deploy.sh` добавлена функция `normalize_backup_permissions`, которая обрабатывает только обычные top-level файлы `*.dump` и `*.dump.json` в server backup directory, устанавливает mode `0644` и завершает deploy с точным путём при неуспешном `chmod`.

Repair запускается после создания обязательных data directories, но до получения target SHA и до early exit для уже установленной revision. Поэтому повторный идемпотентный deploy исправляет legacy artifacts даже без смены кода.

Поиск использует `find -maxdepth 1 -type f -print0`: вложенные каталоги и symlink не затрагиваются, имена с пробелами и переводами строк обрабатываются безопасно.

Deployment contract расширен проверками области поиска, режима `0644`, null-delimited обработки и порядка вызова относительно same-revision early exit.

### Изменённые модули и контракты

- `deploy/server/deploy.sh`: добавлен fail-fast repair legacy backup permissions;
- `tests/test_server_deployment_contract.py`: закреплён новый deployment contract;
- `docs/worklog/2026-08-05-legacy-backup-permission-repair.md`: эксплуатационная запись.

Формат dump, PostgreSQL restore contract, Telegram Storage encryption и deletion policy не изменены.

### Миграции и совместимость

Миграции базы данных, изменения schema и преобразование backup-файлов не требуются. Repair совместим с существующими custom-format PostgreSQL dump и JSON manifest, поскольку изменяет только Unix mode.

Новые predeploy dump уже создаются с mode `0644`, поэтому повторный `chmod 0644` идемпотентен. Файлы других типов, вложенные artifacts и symlink остаются без изменений. На host, где deploy-пользователь не владеет legacy dump и не имеет права менять mode, deployment завершится до checkout/reset и запуска контейнеров с диагностикой конкретного пути.

### Проверки

Guarded patch и локальные контракты:

- patch workflow run `31013808979`: success;
- `bash -n deploy/server/deploy.sh`: success;
- `python -m unittest tests.test_server_deployment_contract -v`: success;
- временный branch-only workflow удалён своим successful commit и отсутствует в итоговом PR diff.

Обязательный CI на проверенном production head `af37e860b34b1b991a94c0a5852d8e5381adb915`:

- tests run `31014069116`: success; preflight, compile, fast architecture contracts и четыре test shard прошли;
- security supply chain run `31014069038`: success; CodeQL Python, static security, ShellCheck и supply-chain contract прошли;
- docker build run `31014068917`: success;
- project notes contract run `31014069118`: success;
- type check run `31014069009`: success;
- branch protection contract run `31014069020`: success.

Два ранних patcher run (`31013502565`, `31013602562`) остановились до commit на генерации тестового текста. Production-файлы ими не изменялись. Финальный patcher использовал явные уровни Python indentation и прошёл собственные guards.

Project notes run `31013956675` корректно обнаружил отсутствовавший обязательный раздел `Миграции и совместимость`; раздел добавлен без изменения production-кода.

### PR и commit

PR: #644 `Repair legacy backup permissions before deploy`.

Production/test commit: `5d08988881c53f3e9e873fc3a06ed9d541a7b98f`.

PR готов к guarded squash merge после подтверждения checks на финальном documentation head.

### Незавершённое

Repository hotfix завершён. Первый deployment после merge исправит фактический host-файл, если deploy-пользователь может выполнить `chmod`. Если файл принадлежит другому UID и mode изменить нельзя, deploy остановится с явной ошибкой; потребуется отдельная host-level смена владельца, после чего deployment и Telegram Storage Migration следует повторить.

### Следующий шаг

Слить PR #644 после финальных checks. Затем развернуть merge commit и повторить Telegram Storage Migration.
