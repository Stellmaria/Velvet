# 2026-07-31 — Server-safe in-bot restart

- Дата: 2026-07-31
- ID: `server-self-restart`
- Issue: без отдельного issue
- Линия/фаза: server operations
- Статус: `завершено`
- Ветка: `agent/server-self-restart`
- Базовый commit: `1a80077a6d4c8a7ef46b2c4464b51af7a0aeb75d`

## Перед началом

### Цель

Сохранить управление перезапуском Velvet из Telegram после переноса production-контура
с Windows Supervisor на Ubuntu, systemd и Docker Compose.

### Исходный контекст

Существующая кнопка отправляла `POST /v1/restart` в локальный Supervisor API и при
отсутствующем `SupervisorClient` возвращала владельцу отказ. В production бот теперь
работает в контейнере с `restart: unless-stopped`, а выдавать приложению Docker socket,
права systemd или произвольный host command contract небезопасно.

### Планируемый объём

- сохранить прежний Supervisor API path для локального режима;
- добавить fallback, корректно завершающий текущий процесс в Docker;
- обновить текст подтверждения под оба runtime-контура;
- защитить операцию от повторного нажатия;
- отправить Telegram-подтверждение до завершения процесса;
- покрыть coordinator unit-тестами;
- не смешивать runtime restart с git deployment.

### Критерии готовности

- кнопка перезапуска работает без подключённого Supervisor;
- при доступном Supervisor сохраняется существующий API contract;
- недоступный Supervisor не блокирует аварийный перезапуск;
- контейнер не получает доступ к Docker socket или systemd;
- повторное подтверждение не создаёт вторую restart-задачу;
- type check, Docker build, unit tests и project notes contract проходят.

### Риски и ограничения

Fallback полагается на внешний runtime, который обязан поднимать завершившийся процесс.
В production это Docker Compose `restart: unless-stopped`; в историческом desktop-контуре
процесс по-прежнему контролирует Supervisor. Обновление кода остаётся отдельным deploy с
backup, smoke, healthcheck и rollback: делать `git pull` из процесса, который сам себя
заменяет, было бы эффектно, но эксплуатационно безответственно.

## После завершения

### Фактически сделано

- добавлен `ProcessRestartCoordinator` с delayed SIGTERM и защитой от duplicate taps;
- существующий Supervisor API restart сохранён как основной path при доступном клиенте;
- при отключённом или недоступном Supervisor используется container-safe fallback;
- Telegram-карточка подтверждает принятие до завершения процесса;
- публичный editing adapter принимает отсутствие follow-up keyboard;
- добавлены async unit-тесты повторного и последовательного restart request.

### Миграции и совместимость

Миграций базы данных нет. Callback payload `restart.ask`/`restart.do`, owner access и
локальный Supervisor API остаются совместимыми. Изменяется только fallback при
отсутствующем или недоступном Supervisor.

### Проверки

Подтверждены в GitHub Actions:

- type check;
- Docker build.

После финализации worklog повторно запускаются full unit tests и project notes contract.
Финальный CI повторно запущен на актуальном head после обновления generated inventory.

### PR и commit

- PR: #486;
- ветка: `agent/server-self-restart`;
- проверяемый head обновлён финальным worklog commit.

### Незавершённое

Кодовый срез завершён. Production smoke выполняется после merge и deploy: проверяется
смена времени запуска контейнера после подтверждения перезапуска в Telegram.

### Следующий шаг

После зелёного CI слить PR #486 и развернуть его через `deploy/server/deploy.sh`, не
подменяя deploy обычным `git pull` и ручным перезапуском.
