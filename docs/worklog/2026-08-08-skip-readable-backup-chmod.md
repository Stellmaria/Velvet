# Пропуск chmod для уже читаемых backup artifacts

- Дата: 2026-08-08
- ID: `2026-08-08-skip-readable-backup-chmod`
- Линия/фаза: hotfix / server deployment reliability
- Статус: `завершено`
- Ветка: `fix/skip-readable-backup-chmod`
- Базовый commit: `ddc62c9587f92c69a51d2084e46ac2086fc7835e`

## Перед началом

### Цель

Не останавливать штатный server deploy на backup-файлах, которые уже читаемы bot container, но принадлежат другому host UID и потому не допускают повторный `chmod` от deploy-пользователя.

### Исходный контекст

На production после merge PR #723 штатный `deploy/server/deploy.sh` остановился до `git fetch` на `normalize_backup_permissions`. Daily dump и его JSON manifest уже имели mode `0644`, но принадлежали UID `10001`. Deploy запускается от пользователя `velvet`, поэтому безусловный `chmod 0644` завершался `Operation not permitted`, хотя фактический contract читаемости для bot container уже был выполнен.

Host-level смена владельца позволила завершить deployment, но это только operational repair. Код должен быть идемпотентен и не пытаться менять mode уже читаемого artifact.

### Планируемый объём

- оставить существующую область нормализации: только top-level regular `*.dump` и `*.dump.json`;
- передавать в `chmod 0644` только файлы без world-read bit;
- не менять ownership, ACL, backup format или directory permissions;
- сохранить fail-fast поведение для действительно нечитаемого файла, mode которого deploy-пользователь не может исправить;
- закрепить новый filter в deployment contract test.

### Критерии готовности

- backup с mode `0644` не попадает в `chmod`, независимо от владельца;
- legacy backup без world-read bit по-прежнему нормализуется через `chmod 0644`;
- symlink, вложенные файлы и другие расширения не затрагиваются;
- новый predeploy dump по-прежнему получает mode `0644`;
- shell parse, deployment contract и обязательные CI checks проходят.

### Риски и ограничения

Проверка `! -perm -004` ориентирована на действующий server contract: backup directory остаётся private, а сам artifact должен иметь read bit для container UID, который может отличаться от host owner. Если файл не имеет world-read bit и deploy-пользователь не владеет им, `chmod` по-прежнему завершится ошибкой с точным путём. Это намеренное fail-fast поведение для реально нечитаемого backup.

## После завершения

### Фактически сделано

В `normalize_backup_permissions` поиск backup artifacts дополнен `! -perm -004`. Поэтому уже читаемые `0644` dump/manifest, включая файлы от UID `10001`, не передаются в `chmod` и не могут остановить deploy только из-за различия владельца.

Файлы без world-read bit остаются кандидатами на repair и получают mode `0644` прежним способом. Счётчик `normalized` теперь отражает только фактически изменяемые artifacts.

Deployment contract расширен проверкой обязательного `! -perm -004` filter. Остальной deployment lifecycle не изменён.

### Изменённые модули и контракты

- `deploy/server/deploy.sh`: пропуск уже bot-readable backup artifacts;
- `tests/test_server_deployment_contract.py`: regression contract для permission filter;
- `docs/worklog/2026-08-08-skip-readable-backup-chmod.md`: запись production-инцидента и решения.

### Миграции и совместимость

Миграции БД и преобразования backup-файлов не требуются. Новый predeploy dump продолжает получать `0644`. Existing backup artifacts с `0644`, `0645`, `0664` и другими mode с установленным other-read bit считаются уже читаемыми и не изменяются; private parent directory по-прежнему ограничивает доступ на host.

Legacy artifacts без other-read bit продолжают нормализоваться до `0644`, если deploy-пользователь имеет право изменить mode.

### Проверки

Обязательный CI запускается через PR после публикации branch head. Проверяются tests, security/supply-chain, Docker build, type check, project notes и branch-protection contracts.

### Незавершённое

Production уже вручную восстановлен и успешно обновлён до базового commit `ddc62c9587f92c69a51d2084e46ac2086fc7835e`. После merge этого hotfix следующий штатный deploy должен подтвердить, что daily backup от UID `10001` с mode `0644` больше не блокирует preflight lifecycle.

### Следующий шаг

Слить PR после полного зелёного CI и неизменившегося проверенного head. Затем выполнить обычный server deploy и проверить revision/health без ручного `chown` backup artifacts.
