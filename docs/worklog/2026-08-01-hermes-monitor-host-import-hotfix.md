# 2026-08-01 — Hotfix host-import Hermes monitor

- Дата: `2026-08-01`
- ID: `hermes-monitor-host-import-hotfix`
- Линия/фаза: `server operations`
- Статус: `частично`
- Ветка: `hotfix/hermes-monitor-host-import`

## Перед началом

### Цель

Остановить restart-loop `velvet-hermes-incident-monitor.service` на Ubuntu VPS и сохранить read-only incident monitoring без установки проектных Python-зависимостей в системный interpreter.

### Исходный контекст

После установки orchestration service запускал `/usr/bin/python3 /srv/velvet/scripts/hermes_incident_monitor.py`. Импорт `velvet_supervisor.hermes_incident` сначала выполнял eager `velvet_supervisor/__init__.py`, который импортировал legacy config и требовал `python-dotenv`. Host Python не содержит эту контейнерную зависимость, поэтому service завершался с `ModuleNotFoundError: dotenv` и перезапускался каждые пять секунд.

### Планируемый объём

- сделать публичные exports `velvet_supervisor` ленивыми;
- не импортировать legacy config/runtime при загрузке stdlib-only submodules;
- ограничить systemd restart burst;
- добавить regression test отдельного Python process;
- выполнить CI и повторный VPS smoke после merge.

### Критерии готовности

- `import velvet_supervisor.hermes_incident` не загружает `velvet_supervisor.config`;
- `import velvet_supervisor.notifier` не загружает legacy runtime;
- публичные `SupervisorSettings` и `VelvetSupervisor` остаются доступны через lazy attributes;
- monitor unit использует bounded restart policy;
- CI зелёный;
- после deploy service имеет `active/running`, `ExecMainStatus=0` и не увеличивает `NRestarts`.

## После завершения

Статус: `частично`.

### Фактически сделано

- `velvet_supervisor/__init__.py` переведён на PEP 562 lazy attributes;
- lightweight incident/notifier modules больше не подтягивают `python-dotenv`;
- unit получил `StartLimitIntervalSec=60`, `StartLimitBurst=3` и `Restart=on-failure`;
- добавлен subprocess regression test на отсутствие legacy imports.

### Миграции и совместимость

SQL и runtime data не изменяются. Установка `python-dotenv` в host Python не требуется. Legacy Windows Supervisor продолжает получать те же публичные классы при обращении к ним.

### Проверки

- GitHub Actions CI после открытия PR;
- после merge: обновление `/srv/velvet`, переустановка unit и host import smoke.

### PR и commit

- PR будет создан из `hotfix/hermes-monitor-host-import`;
- production пока не изменён.

### Незавершённое

- дождаться CI;
- слить PR;
- обновить VPS и подтвердить стабильный service.

### Следующий шаг

Открыть hotfix PR и проверить все обязательные workflow.
