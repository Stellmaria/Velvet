# Hermes Infrastructure Reconcile

Этот контур позволяет главному Каэлю после явного разрешения владельца переустанавливать только заранее определённые Hermes-компоненты после обновления `/srv/velvet`:

```text
coders
entities
librarian
all
```

Он не заменяет `opsctl update`. Сначала production checkout Velvet должен быть обновлён обычным Supervisor-маршрутом. Reconcile только применяет уже находящиеся в чистом `main` installer/systemd-изменения.

## Граница безопасности

Каэль не получает:

- root или `sudo`;
- Docker socket;
- systemd API;
- production `.env`;
- GitHub tokens кодеров;
- произвольный shell, путь, service name или commit SHA.

Контур разделён на три части:

1. `/opt/data/tools/reconcilectl.py` внутри Каэля принимает только `submit/status/wait/list`.
2. `hermes-reconcile-gateway` работает непривилегированно, не имеет published ports и видит только dedicated Unix socket.
3. `hermes-operator-reconcile.service` работает на host как root, но исполняет только фиксированный allowlist installer-команд.

Перед созданием задачи host bridge проверяет:

- checkout ровно `/srv/velvet`;
- активная ветка `main`;
- рабочее дерево чистое, включая untracked files;
- `HEAD` совпадает с уже fetched `refs/remotes/origin/main`.

Bridge не выполняет `git fetch`, checkout, reset, merge или произвольные команды. Обновление Git остаётся обязанностью Supervisor.

## Асинхронный lifecycle

Reconcile создаётся асинхронно, потому что `entities` в конце перезапускает основной runtime Каэля. Сначала Каэль получает `task_id`, затем root bridge выполняет работу независимо от Telegram-сессии.

Для `all` порядок фиксирован:

```text
coders → librarian → entities
```

`entities` идёт последним, чтобы self-restart Каэля не прервал установку остальных компонентов.

История последних 100 задач хранится в:

```text
/srv/hermes-operator-control/reconcile-state/tasks.json
```

Файл доступен только root. В него не записывается полный stdout, токены или секреты. При ошибке сохраняется только очищенный ограниченный хвост диагностики.

## Установка

После merge и обновления `/srv/velvet` один раз требуется доверенный host install:

```bash
cd /srv/velvet
sudo bash deploy/hermes-reconcile/install.sh
```

Installer:

- сохраняет существующий `HERMES_OPS_CLIENT_TOKEN`;
- создаёт отдельный reconcile token без вывода значения;
- устанавливает root bridge в `/usr/local/libexec`;
- устанавливает host и gateway systemd units;
- копирует `reconcilectl.py` в data directory Каэля;
- обновляет `AGENTS.md` через штатный entities reconcile;
- проверяет доступ gateway из контейнера Каэля.

## Использование Каэлем

```bash
python /opt/data/tools/reconcilectl.py submit coders
python /opt/data/tools/reconcilectl.py submit entities
python /opt/data/tools/reconcilectl.py submit librarian
python /opt/data/tools/reconcilectl.py submit all

python /opt/data/tools/reconcilectl.py status <task_id>
python /opt/data/tools/reconcilectl.py wait <task_id>
python /opt/data/tools/reconcilectl.py list
```

Для `entities` и `all` Каэль должен сначала сообщить владельцу `task_id`. Во время выполнения его контейнер будет перезапущен. После восстановления он проверяет `status <task_id>` или `list` и только тогда сообщает итог.

## Production-порядок

1. Проверить merged PR и зелёный CI.
2. Получить явное разрешение владельца на update.
3. Выполнить `opsctl.py velvet update`.
4. Дождаться terminal `success` и подтвердить новый commit.
5. Получить отдельное явное разрешение на infrastructure reconcile, если оно не было дано в том же запросе.
6. Выполнить `reconcilectl.py submit <target>`.
7. Проверить terminal status задачи.
8. Выполнить component-specific smoke:
   - coders: `runtime_smoke.py` уже входит в фиксированную задачу;
   - entities: `coderctl.py health all`, права ledger и имя Каэля проверяет installer;
   - librarian: bot-to-Librarian health проверяет installer.

`accepted` или наличие процесса не считается доказательством успешного reconcile.
