# 2026-07-31 — Linux deploy runtime permissions

- Дата: 2026-07-31
- ID: linux-deploy-runtime-permissions
- Линия/фаза: hotfix/эксплуатация Linux VPS
- Статус: завершено
- Ветка: `agent/linux-deploy-runtime-permissions`
- Базовый commit: `6cdf6c6e8a018d544956d64ddc9738f446fe5965`

## Перед началом

### Цель

Устранить фактические причины отказа production deploy на Linux VPS после слияния политики цен VL.

### Исходный контекст

Deploy успешно создал и проверил PostgreSQL dump, затем Docker build остановился на недоступном каталоге `/srv/velvet/data/hermes.backup-*`. После автоматического отката работающий бот остался на предыдущем commit. Отдельно Telegram storage не мог прочитать predeploy dump из-за режима `0600` при различающихся UID host-пользователя и bot-контейнера.

### Планируемый объём

- исключить весь runtime-каталог `data` из Docker build context;
- сохранить закрытый parent-каталог backups, но разрешить bot-контейнеру читать verified predeploy dump;
- закрепить оба требования deployment-contract тестами.

### Критерии готовности

- Docker build не обходит runtime data и Hermes backup-каталоги;
- новый predeploy dump читается bot-контейнером;
- deploy по-прежнему проверяет dump до переключения кода;
- shell и deployment tests проходят.

### Риски и ограничения

Старые dump-файлы на уже развернутом VPS сохраняют прежние права до отдельного `chmod`. Текущий работающий контейнер и база не изменяются этим PR.

## После завершения

### Фактически сделано

- `.dockerignore` теперь исключает весь `data` вместо неполного списка отдельных runtime-путей;
- `deploy/server/deploy.sh` создаёт verified predeploy dump с режимом `0644`, при этом parent backup directory остаётся закрытым;
- добавлены regression tests для Docker build context и доступности dump контейнеру.

### Миграции и совместимость

Миграции базы не добавлялись. Изменение совместимо с текущим Docker Compose и не меняет формат backup.

### Проверки

- контракт `.dockerignore` проверяет исключение `data` и `server-data`;
- deployment test проверяет `chmod 0644` и отсутствие прежнего `chmod 600`;
- существующий bash syntax contract продолжает проверять deploy scripts.

### PR и commit

Изменения подготовлены в `agent/linux-deploy-runtime-permissions`; PR и итоговый merge commit будут зафиксированы после CI.

### Незавершённое

На VPS перед повторным deploy требуется один раз сделать существующие `.dump` читаемыми контейнеру и затем повторно запустить штатный deploy.

### Следующий шаг

Слить hotfix после зелёного CI, выполнить `chmod 0644 /srv/velvet/data/backups/*.dump` и повторить `deploy/server/deploy.sh`.
