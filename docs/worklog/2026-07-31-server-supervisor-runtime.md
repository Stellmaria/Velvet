# 2026-07-31 — Server Supervisor для Docker production

- Дата: `2026-07-31`
- ID: `server-supervisor-runtime`
- Линия/фаза: `server operations`
- Статус: `частично`
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

- добавлен отдельный `scripts/server_supervisor.py`, запускаемый systemd на хосте пользователем `velvet`;
- сохранён существующий HTTP contract `/v1/status`, `/v1/logs`, `/v1/restart`, `/v1/update`, `/v1/rollback` и self-restart endpoints;
- restart вызывает только `docker compose restart bot` и ожидает healthcheck;
- update и rollback запускают единый `deploy/server/deploy.sh` и возвращают operation ID до остановки контейнера;
- deploy получил проверяемый target override для rollback и разрешает только commit-предок актуального `origin/main`;
- состояние операций и rollback SHA сохраняются в постоянном runtime-каталоге;
- добавлен non-root proxy image, который имеет только runtime mount и private Compose network;
- proxy не получает Docker socket, checkout, systemd, production env или host port;
- добавлены systemd unit, повторно запускаемый installer и Compose wiring;
- installer включает server endpoint, создаёт случайный bearer secret при отсутствии пригодного значения и не меняет владельцев общих runtime/logs каталогов;
- общий deploy lock остаётся общим для SSH и systemd runtime;
- Windows-пакет `velvet_supervisor` не изменён и отмечен deprecated только в server documentation/status.

### Миграции и совместимость

SQL-миграций нет. Telegram callback payload и `SupervisorClient` не меняются. Windows runtime остаётся совместимым и изолирован от нового server runtime.

### Проверки

- новые Python scripts успешно прошли compilation-проверку;
- Unix HTTP health endpoint проверен через реальный AF_UNIX socket;
- добавлен `tests/test_server_supervisor_contract.py` для fixed actions, systemd sandbox, proxy isolation, deploy rollback gate и installer behavior;
- GitHub Actions на функциональной голове полностью зелёные: `project notes contract`, `type check`, `docker build` и полный `tests` workflow;
- Docker job подтвердил сборку bot, Krita и отдельного Server Supervisor proxy image, Compose validation и синтаксис deployment scripts.

### PR и commit

- PR: `#496`;
- ветка: `agent/server-supervisor-runtime`;
- функциональная голова с полностью зелёным CI: `85565023e5691d337ccea2bfaf9772420d3a9b6f`;
- последующий documentation-only commit фиксирует фактический результат CI;
- merge выполняется только после зелёной повторной проверки документационной головы.

### Незавершённое

- после merge обновить `/srv/velvet` обычным SSH deploy;
- установить unit командой `sudo bash deploy/server/install-server-supervisor.sh`;
- проверить `/supervisor`, restart, update no-op и последующий реальный update;
- подтвердить, что PostgreSQL и Hermes сохраняют прежние StartedAt при restart бота.

### Следующий шаг

Дождаться зелёной повторной проверки documentation-only commit, перевести PR в ready и затем отдельно принять решение о merge и live smoke на VPS.
