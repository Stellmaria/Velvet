# Server housekeeping: Compose Bake и BuildKit cache timer

- Дата: 2026-08-08
- ID: `2026-08-08-server-housekeeping`
- Линия/фаза: server operations / housekeeping
- Статус: `завершено`
- Ветка: `fix/server-housekeeping`
- Базовый commit: `e908c33bccb2062f679f45becbb839ff90096c68`

## Перед началом

### Цель

Закрыть оставшиеся housekeeping-пункты текущей production-сессии: убрать предупреждение `COMPOSE_BAKE=false is deprecated` из штатного Velvet server deploy/Supervisor пути и закрепить безопасную еженедельную очистку старого Docker BuildKit cache без удаления runtime images, containers, networks или volumes.

Ubuntu package updates остаются отдельной host-операцией после merge и не маскируются как изменение репозитория.

### Исходный контекст

Production deploy 2026-08-08 успешно завершился, но Docker Compose несколько раз печатал предупреждение о deprecated `COMPOSE_BAKE=false`. Исторически это значение было введено вместе с `ProtectHome=read-only`, чтобы Compose не писал buildx metadata в `/home/velvet/.docker`. Позже Server Supervisor и deploy получили отдельный writable `DOCKER_CONFIG=/srv/velvet/data/runtime/docker-config`, поэтому принудительное отключение Bake больше не требуется.

Отдельно в этой же сессии ручной `docker builder prune -af` показал, что основной источник лишнего дискового использования был BuildKit cache. Нужен ограниченный периодический prune вместо опасного общего `docker system prune -a`.

### Планируемый объём

- включить Compose Bake по умолчанию в `deploy/server/deploy.sh`, сохранив возможность explicit override через environment;
- включить Compose Bake в `velvet-server-supervisor.service` при сохранении writable `DOCKER_CONFIG`;
- добавить weekly oneshot/timer для `docker builder prune -af --filter until=168h`;
- сериализовать prune тем же `/tmp/velvet-deploy.lock`, что использует deploy;
- при активном deploy пропускать prune без ошибки и дождаться следующего timer run;
- запускать maintenance service от `velvet`, не от root;
- добавить installer и regression contracts.

### Критерии готовности

- Velvet deploy/Supervisor больше не задают `COMPOSE_BAKE=false`;
- server deploy использует `COMPOSE_BAKE=true` по умолчанию и сохраняет отдельный writable `DOCKER_CONFIG`;
- timer запускается раз в неделю, persistent и с jitter;
- prune затрагивает только BuildKit cache старше 168 часов;
- prune не запускается одновременно с deploy;
- service не использует `docker system prune`, `image prune` или `volume prune`;
- shell parse и обязательный CI проходят.

### Риски и ограничения

Compose Bake использует Buildx/BuildKit. Production уже собирает образы через BuildKit, а writable `DOCKER_CONFIG` сохраняется, поэтому старое ограничение read-only home не возвращается. При необходимости оператор всё ещё может явно передать `COMPOSE_BAKE=false` на время диагностики, пока текущая версия Compose поддерживает такой override, хотя сам Docker помечает этот режим deprecated.

Weekly prune удаляет только неиспользуемый build cache, подходящий под `until=168h`. Активные images, containers, networks, named volumes и model blobs этой командой не удаляются.

## После завершения

### Фактически сделано

`deploy/server/deploy.sh` теперь использует `COMPOSE_BAKE=true` как default. `velvet-server-supervisor.service` задаёт такое же значение и продолжает использовать `/srv/velvet/data/runtime/docker-config`.

Добавлен `deploy/server/prune-build-cache.sh`: он валидирует возраст cache, использует общий deploy lock и выполняет только `docker builder prune -af --filter until=168h`. Если deploy уже держит lock, maintenance run завершается успешно с сообщением о пропуске.

Добавлены systemd oneshot service и weekly timer. Timer запускается по воскресеньям в 04:15 UTC, имеет `RandomizedDelaySec=30m` и `Persistent=true`. Service работает от `velvet`, имеет `NoNewPrivileges=true` и не получает private `/tmp`, чтобы видеть общий deploy lock.

Добавлен root installer, который устанавливает обе unit-файла, делает `daemon-reload` и включает только timer.

### Изменённые модули и контракты

- `deploy/server/deploy.sh`: Compose Bake default;
- `deploy/systemd/velvet-server-supervisor.service`: Compose Bake environment;
- `deploy/server/prune-build-cache.sh`: conservative BuildKit cleanup;
- `deploy/server/install-build-cache-prune.sh`: timer installer;
- `deploy/systemd/velvet-build-cache-prune.service`: unprivileged oneshot maintenance;
- `deploy/systemd/velvet-build-cache-prune.timer`: weekly persistent schedule;
- `tests/test_server_supervisor_contract.py`: updated Bake contract;
- `tests/test_server_housekeeping_contract.py`: cleanup/timer safety contracts.

### Миграции и совместимость

SQL-миграций нет. Docker images, runtime containers, persistent volumes и backup format не меняются. Timer не требует изменения `.env.server`; age override доступен через `VELVET_BUILD_CACHE_PRUNE_AGE` в service environment при ручной настройке unit.

### Проверки

Regression contracts проверяют отсутствие deprecated default в production deploy/Supervisor, точную ограниченную prune-команду, общий deploy lock, отсутствие destructive prune-команд, weekly persistent timer, запуск service от `velvet` и shell syntax новых scripts.

Полный required CI выполняется на PR head перед merge.

### PR и commit

PR создаётся из `fix/server-housekeeping` после проверки diff. Merge выполняется только после полного зелёного required CI и повторной проверки актуальности относительно `main`.

### Незавершённое

После merge нужно применить новый код и unit-файлы на VPS, включить timer и отдельно установить доступные Ubuntu package updates. Если `/var/run/reboot-required` появится после apt upgrade, reboot выполняется только после проверки состояния production и затем подтверждается повторным health check.

### Следующий шаг

Проверить branch diff, открыть PR, дождаться required CI и слить. Затем выполнить штатный server deploy, установить `velvet-build-cache-prune.timer`, проверить `systemctl list-timers`, выполнить Ubuntu package upgrade и финальный production health check.
