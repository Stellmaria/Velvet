# 2026-07-31 — Server Supervisor для Docker production

- Дата: `2026-07-31`
- ID: `server-supervisor-runtime`
- Линия/фаза: `server operations`
- Статус: `в работе`
- Ветка: `agent/server-supervisor-runtime`
- Базовый commit: `4eafd7c14d27822dad4d88d8788d76acce57130a`

## Перед началом

### Цель

Вернуть владельцу управление Velvet из Telegram после переноса production с Windows на Ubuntu и Docker Compose: просмотр состояния, логов, перезапуск только контейнера бота, безопасное обновление из `origin/main` и откат на предыдущий проверенный commit.

### Исходный контекст

Telegram-интерфейс Supervisor и HTTP-клиент уже существовали, но production VPS не запускал Windows-ориентированный `velvet_supervisor`. После PR #486 команда `/restart` могла завершить процесс внутри контейнера, однако главное меню Supervisor, Git update и rollback оставались недоступными без отдельного Supervisor API.

Старый Windows runtime может снова понадобиться для локального desktop-контура, поэтому его нельзя переписывать под Linux или удалять.

### Планируемый объём

- сохранить пакет `velvet_supervisor` как deprecated Windows runtime без функциональных изменений;
- добавить отдельный host-side systemd runtime для Ubuntu;
- сохранить существующий HTTP API contract, чтобы Telegram-клиент и кнопки продолжили работать;
- соединить контейнер бота с host runtime через Unix socket и изолированный TCP proxy внутри Compose network;
- запретить proxy доступ к Docker socket, checkout, systemd, production secrets и host ports;
- разрешить host runtime только фиксированные операции restart, update, rollback, status и logs;
- выполнять update и rollback только через штатный `deploy/server/deploy.sh` с backup, restore verification, build, healthcheck, smoke и automatic code rollback;
- добавить installer, systemd unit, deployment contracts и Docker CI.

### Критерии готовности

- `/supervisor` открывается на VPS и показывает состояние server runtime;
- `Перезапустить бот` перезапускает только Compose service `bot`;
- `Обновить main` запускает штатный deploy и возвращает Telegram operation ID до остановки контейнера;
- откат допускается только на сохранённый commit, являющийся предком `origin/main`;
- PostgreSQL, Hermes и VPS не перезапускаются при restart бота;
- бот и proxy не получают `docker.sock` или root privileges;
- старый Windows Supervisor остаётся в репозитории и не импортируется server runtime;
- unit tests, Docker Compose validation, Python compilation и Docker image builds проходят.

### Риски и ограничения

Server Supervisor является привилегированным только относительно пользователя `velvet`, который уже управляет production Compose. Поэтому API доступен исключительно через Unix socket, защищён bearer token и не публикует host port. Произвольная консоль и Codex actions намеренно отключены в server runtime.

Откат к старому коду не восстанавливает базу автоматически. Перед каждым update и rollback всё равно создаётся и полностью проверяется PostgreSQL dump, а путь к нему сохраняется в operation output.

## После завершения

### Фактически сделано

Будет заполнено после зелёного CI и live smoke на VPS.

### Проверки

Будет заполнено после CI.

### Миграции и совместимость

SQL-миграций нет. Telegram callback payload и `SupervisorClient` не меняются. Windows runtime остаётся совместимым и получает статус deprecated только в документации server-контура.

### PR и commit

Будет заполнено после открытия PR.

### Незавершённое

- дождаться полного CI;
- установить unit на VPS;
- проверить `/supervisor`, restart, update no-op и последующий реальный update;
- подтвердить, что PostgreSQL и Hermes сохраняют прежние StartedAt при restart бота.

### Следующий шаг

Открыть draft PR, устранить замечания CI, затем установить server runtime командой `sudo bash deploy/server/install-server-supervisor.sh` после merge и обычного SSH deploy.
