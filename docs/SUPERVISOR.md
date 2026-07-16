# Velvet Supervisor и Codex

`Velvet Supervisor` запускается отдельным процессом и владеет жизненным циклом
основного Telegram-бота. Это позволяет перезапускать бот, обновлять Git и
собирать логи, даже если дочерний процесс завершился с ошибкой.

## Архитектура

```text
Telegram-команды владельца
        ↓
Velvet Bot
        ↓ localhost + Bearer token
Velvet Supervisor
        ├── запускает main.py
        ├── пишет logs/velvet.log
        ├── ограничивает crash-loop
        ├── выполняет fetch/fast-forward/tests/restart
        ├── откатывает неудачное обновление
        └── запускает Codex в отдельном Git worktree
```

Supervisor не принимает Telegram updates и не конкурирует с основным ботом за
polling. Для уведомлений он использует `BOT_TOKEN` только для `sendMessage` в
`SUPERVISOR_NOTIFICATION_CHAT_ID` или `LOG_CHAT_ID`.

## Установка

1. Обновите проект и зависимости.
2. Создайте случайный локальный токен:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

3. Добавьте в `.env`:

```env
SUPERVISOR_ENABLED=true
SUPERVISOR_TOKEN=вставьте_случайный_токен
SUPERVISOR_HOST=127.0.0.1
SUPERVISOR_PORT=8765
SUPERVISOR_BASE_URL=http://127.0.0.1:8765
SUPERVISOR_BOT_COMMAND=".venv314\Scripts\python.exe" main.py
SUPERVISOR_TEST_COMMAND=".venv314\Scripts\python.exe" -m unittest discover -s tests -v
```

Параметр `SUPERVISOR_TOKEN` один и тот же для Supervisor и основного бота.
HTTP API по умолчанию слушает только loopback-интерфейс.

4. Запускайте не `main.py`, а Supervisor:

```powershell
.\.venv314\Scripts\python.exe -m velvet_supervisor
```

Supervisor сам запустит `main.py`.

## Команды Telegram

Все команды проходят существующий owner-only middleware:

```text
/supervisor
/status
/logs
/restart
/update
/rollback
/codex <задача>
/codex_status <task_id>
```

`/update` выполняет:

1. проверку чистого рабочего дерева;
2. `git fetch --prune origin main`;
3. `git merge --ff-only origin/main`;
4. полный набор тестов;
5. перезапуск;
6. проверку, что процесс не завершился в течение startup grace;
7. автоматический возврат предыдущего commit при ошибке.

`/rollback` возвращает последнее развёртывание, записанное Supervisor.

## Crash-loop защита

По умолчанию разрешено не более трёх автоматических перезапусков за десять
минут:

```env
SUPERVISOR_MAX_RESTARTS=3
SUPERVISOR_RESTART_WINDOW_SECONDS=600
```

После превышения лимита Supervisor оставляет процесс остановленным и отправляет
последние строки журнала в служебный чат. Ручной `/restart` очищает счётчик.

## Логи

```text
logs/velvet.log
logs/velvet.log.1
logs/supervisor.log
```

Журнал дочернего процесса ротируется: 10 файлов по 10 МБ. Строки с traceback,
ERROR или CRITICAL отправляются в служебный чат с дедупликацией.

## Codex

Codex необязателен. Supervisor, обновления и перезапуски работают без него.

Установите Codex CLI, откройте каталог проекта и один раз запустите:

```powershell
codex
```

При первом запуске выберите `Sign in with ChatGPT` и завершите вход в браузере.

Затем включите:

```env
CODEX_ENABLED=true
CODEX_COMMAND=codex exec --json --sandbox workspace-write -
CODEX_TIMEOUT_SECONDS=1800
CODEX_WORKTREE_DIR=runtime/supervisor/codex-worktrees
```

Для каждой задачи Supervisor:

1. создаёт ветку `codex/<task_id>` и отдельный worktree;
2. передаёт Codex только текст задачи и правила безопасности;
3. запрещает добавлять `.env`, ключи, `logs`, `runtime` и `backups`;
4. запускает тесты;
5. создаёт локальный commit;
6. показывает diff и список файлов в Telegram;
7. ждёт явного подтверждения;
8. после подтверждения делает fast-forward, снова запускает тесты и
   перезапускает бот;
9. при ошибке возвращает прежний commit.

Push в `main` выполняется отдельной кнопкой только после применения задачи.

## Запуск через Планировщик Windows

Скрипт регистрации:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\register_supervisor_task.ps1
```

Он создаёт задачу `VelvetSupervisor`, запускаемую при входе пользователя.
Перед регистрацией убедитесь, что путь к Python в `.env` и виртуальное окружение
существуют.

Удаление задачи:

```powershell
schtasks /Delete /TN VelvetSupervisor /F
```

## Основные настройки

```env
SUPERVISOR_AUTO_RESTART=true
SUPERVISOR_STARTUP_GRACE_SECONDS=12
SUPERVISOR_COMMAND_TIMEOUT_SECONDS=900
SUPERVISOR_UPDATE_REMOTE=origin
SUPERVISOR_UPDATE_BRANCH=main
SUPERVISOR_LOG_DIR=logs
SUPERVISOR_RUNTIME_DIR=runtime/supervisor
SUPERVISOR_NOTIFICATION_CHAT_ID=
SUPERVISOR_NOTIFICATION_BOT_TOKEN=
```

Если токен уведомлений не указан, используется `BOT_TOKEN`. Если chat ID не
указан, используется `LOG_CHAT_ID`.
