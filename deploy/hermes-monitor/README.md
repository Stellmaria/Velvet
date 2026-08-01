# Hermes Read-only Monitor

Отдельный контур наблюдения за host runtime для главного Каэля. Он не расширяет `command_allowlist` и не передаёт Каэлю root, Docker socket, systemd API или произвольный shell.

## Фиксированные представления

```text
summary
resources
containers
services
gpu
models
processes
incidents
```

Каэль вызывает только:

```bash
python /opt/data/tools/monitorctl.py summary
python /opt/data/tools/monitorctl.py resources
python /opt/data/tools/monitorctl.py containers
python /opt/data/tools/monitorctl.py services
python /opt/data/tools/monitorctl.py gpu
python /opt/data/tools/monitorctl.py models
python /opt/data/tools/monitorctl.py processes
python /opt/data/tools/monitorctl.py incidents
```

## Граница безопасности

- HTTP gateway не публикует host port и доступен только внутри `velvet_backend`.
- Gateway работает от UID 10001, read-only filesystem, без capabilities и без Docker socket.
- Root host bridge принимает ровно `{token, view}` через dedicated Unix socket.
- Нет пользовательских аргументов, путей, unit names, container names, PID или команд.
- Все subprocess-команды являются фиксированными read-only запросами.
- Process command line не возвращается. Доступны только PID, user, `comm`, CPU, memory, elapsed time и state.
- Docker env, mounts, labels, command и полный inspect payload не возвращаются.
- Journal ограничен warning..alert за последние 30 минут, 100 событиями и редактированием token-like значений.
- `POST`, `PUT` и `DELETE` всегда возвращают `405 Read-only gateway`.

## Установка

После merge и обновления `/srv/velvet`:

```bash
cd /srv/velvet
git pull --ff-only origin main
sudo bash deploy/hermes-monitor/install.sh
```

Installer создаёт отдельный host token, ставит два systemd unit, копирует `monitorctl.py` и актуальный `AGENTS.md` в data directory Каэля, перезапускает Каэля и проверяет `monitorctl summary` из его контейнера.

## Что monitor не делает

- не перезапускает и не останавливает процессы;
- не выполняет Docker mutations;
- не меняет systemd units;
- не читает `.env` и process cmdline;
- не выполняет произвольный `journalctl`;
- не заменяет `opsctl`, `coderctl` и `reconcilectl`.
