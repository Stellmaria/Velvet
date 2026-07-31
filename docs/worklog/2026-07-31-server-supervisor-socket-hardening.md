# Server Supervisor socket hardening

- Дата: 2026-07-31
- ID: issue-509-server-supervisor-socket-hardening
- Линия/фаза: production security / Server Supervisor
- Статус: `частично`
- Ветка: `agent/issue-509-supervisor-socket-hardening`
- Базовый commit: `d955a6e8e71609b83b4324c9ba5dc04e73debeed`

## Перед началом

### Цель

Закрыть world-writable Unix socket Server Supervisor и сделать доступ к privileged restart/update/rollback API двухфакторным на уровне локального control plane: filesystem/peer identity плюс bearer token.

### Исходный контекст

Host Supervisor создавал socket внутри общего `${VELVET_DATA_DIR}/runtime`, выставлял mode `0666`, а весь runtime монтировался в bot, Krita и proxy. Bearer token ограничивал HTTP actions, но любой локальный процесс мог подключиться к socket, а граница файловой системы не выражала intended caller.

### Планируемый объём

- вынести socket в отдельный control directory;
- создать dedicated host group для proxy;
- согласовать numeric UID/GID host и container;
- выставлять mode `0660` и проверять metadata после bind;
- проверять Linux `SO_PEERCRED` до HTTP auth;
- добавить auth failure cooldown без записи token;
- не отдавать наружу raw command exceptions;
- добавить contract и live Unix-socket tests;
- сохранить fixed-action API и существующий proxy contract.

### Критерии готовности

- bot/Krita/Hermes не получают mount control socket;
- proxy видит только read-only control directory;
- socket имеет owner host Supervisor, dedicated group и mode `0660`;
- peer UID/GID проверяется до `/health` и privileged routes;
- bearer token остаётся обязательным для `/v1/*`;
- stale non-socket или socket с неверным owner/group/mode не заменяется;
- repeated invalid token получает cooldown;
- unit/contract tests проходят;
- live systemd/Compose smoke фиксируется отдельно на VPS.

### Риски и ограничения

- numeric GID dedicated group зависит от конкретного VPS и должен записываться installer в `.env.server`;
- `SO_PEERCRED` является Linux contract, поэтому remote Windows Supervisor не затрагивается;
- live проверка чужого local user и реального proxy container требует production-equivalent host и не может быть доказана только repository CI;
- краткий control-plane outage во время переустановки unit допустим, bot продолжает работать, но Supervisor actions временно недоступны.

## После завершения

### Фактически сделано

- socket перенесён в `${VELVET_DATA_DIR}/control/supervisor`;
- proxy монтирует только dedicated directory в `/run/velvet-supervisor:ro`;
- installer создаёт `velvet-supervisor-client`, добавляет `velvet` в supplementary group и записывает numeric UID/GID;
- systemd unit использует `SupplementaryGroups` и `UMask=0007`;
- runtime применяет и перепроверяет `0660`, owner и group;
- каждый request проверяет `SO_PEERCRED`; разрешены configured proxy principal и root maintenance client;
- invalid bearer attempts имеют bounded window/cooldown и логируются только по UID/GID/path;
- operation/API errors наружу редактируются, full exception остаётся в protected host log;
- stale path проверяется по type/owner/group/mode до unlink;
- добавлены contract tests и Unix socket behavior tests.

### Миграции и совместимость

Database migration отсутствует. Installer удаляет только legacy socket-файл старого runtime path после остановки service и отказывается удалять любой non-socket объект. Существующий HTTP contract, routes и bearer token сохраняются. `.env.server` дополняется generated socket UID/GID/mode и rate-limit settings.

### Проверки

- `python -m py_compile scripts/server_supervisor.py`;
- `bash -n deploy/server/install-server-supervisor.sh`;
- `python -m unittest tests.test_server_supervisor_security -v`;
- repository CI: ожидается после публикации PR;
- live systemd/Compose/socket ownership smoke: не выполнен в этой среде.

### PR и commit

PR создаётся из `agent/issue-509-supervisor-socket-hardening` в `main`. Итоговый commit и PR number будут зафиксированы в GitHub issue #509.

### Незавершённое

- проверить на VPS, что proxy process имеет expected peer UID/GID;
- проверить отказ подключения отдельного непривилегированного host user;
- проверить restart/update/rollback через Telegram после installer rerun;
- подтвердить отсутствие control mount в фактических bot/Krita/Hermes containers;
- после live acceptance закрыть #509 и обновить #515.

### Следующий шаг

Запустить полный CI, устранить замечания review, затем применить installer на VPS и выполнить permission/peer/auth smoke до merge либо сразу после безопасного staging deployment.
