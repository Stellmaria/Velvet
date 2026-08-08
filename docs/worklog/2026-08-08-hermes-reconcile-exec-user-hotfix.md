# Hermes reconcile exec-user hotfix

- Дата: 2026-08-08
- ID: hermes-reconcile-exec-user-hotfix-20260808
- Линия/фаза: Hermes reconcile / production acceptance
- Статус: `частично`
- Ветка: `fix/hermes-reconcile-exec-user`
- Базовый commit: `8b160db820592c36f51da491b0525754f6954bdf`

## Перед началом

### Цель

Убрать ложный production failure `deploy/hermes-reconcile/install.sh` после успешной установки reconcile bridge/gateway. Installer должен проверять `reconcilectl.py` под фактическим владельцем Hermes data volume, а не считать default root identity команды `docker compose exec` доказательством неверного runtime UID.

### Исходный контекст

Во время production rollout Storage Librarian на source `8b160db820592c36f51da491b0525754f6954bdf` основной verified deploy прошёл успешно, затем `deploy/hermes-reconcile/install.sh` установил fixed reconcile bridge, перезапустил Hermes и после этого завершился `1` без явной ошибки.

Read-only production diagnostics подтвердили:

- `hermes-operator-reconcile.service` active;
- `hermes-reconcile-gateway.service` active;
- gateway health доступен из Hermes;
- reconcile socket существует с ожидаемыми permissions;
- installed `host_reconcile_entrypoint.py` содержит host-visible `TMPDIR` fix при сохранённом `PrivateTmp=true`;
- `/opt/data/tools/reconcilectl.py` имеет mode `0500`, owner uid/gid `10000:10000` и `--help` возвращает `0`;
- обычный `docker compose exec -T hermes` сообщает `uid=0 gid=0`, потому что container configured user остаётся root для s6-overlay bootstrap;
- `STORAGE_LIBRARIAN_AUTO_ENQUEUE=false` и `STORAGE_LIBRARIAN_AUTO_BACKFILL=false`, поэтому архивный scheduler во время диагностики не запускался.

Следовательно, production failure был вызван только hard-coded installer assertion `test "$(id -u)" = "10000"`, выполненным через default root `docker compose exec`.

### Планируемый объём

- Не менять Hermes image, s6-overlay bootstrap или container-level configured user.
- Сохранить ownership/mode установленного `reconcilectl.py`.
- Выполнять installer acceptance check через `docker compose exec --user "$hermes_uid:$hermes_gid"`.
- Передавать ожидаемые uid/gid как отдельные env values и проверять оба значения.
- Запускать `reconcilectl.py --help` под тем же непривилегированным identity.
- Добавить regression contract, который запрещает возврат hard-coded default-exec UID assertion.
- Не менять Librarian scheduler, full-archive flags, Ollama routing или systemd sandbox.

### Критерии готовности

- Installer больше не содержит `test "$(id -u)" = "10000"` для default `docker compose exec`.
- Acceptance command явно использует `--user "$hermes_uid:$hermes_gid"`.
- Проверяются и uid, и gid владельца Hermes data directory.
- `reconcilectl.py --help` выполняется под тем же identity.
- Existing PrivateTmp/TMPDIR regression остаётся зелёным.
- `hermes reconcile`, tests, type check, project notes, security supply chain, docker build и branch protection contracts проходят на exact PR head.
- Merge выполняется без обхода branch protection.

### Риски и ограничения

- Этот hotfix не меняет уже работающий production bridge до следующей переустановки control plane; текущий runtime уже функционален, сбой относится к installer acceptance.
- Full archive нельзя считать включённым до отдельного `enable_full_archive.sh`; оба background flags на production пока false.
- Проверка через numeric uid/gid намеренно не требует записи пользователя в `/etc/passwd` внутри container.
- Vision и другие runtime контуры не входят в scope.

## После завершения

### Фактически сделано

- `deploy/hermes-reconcile/install.sh` теперь запускает финальный reconcile-client smoke через `docker compose exec --user "$hermes_uid:$hermes_gid"`.
- Installer передаёт `EXPECTED_UID` и `EXPECTED_GID`, проверяет оба значения и только затем запускает `python /opt/data/tools/reconcilectl.py --help`.
- Убрана ложная связь между default `docker compose exec` identity и фактическим владельцем Hermes data volume.
- Добавлен regression test в `tests/test_hermes_reconcile_checkout_entrypoint.py`, который требует owner-user exec и запрещает старый hard-coded assertion.
- Production evidence зафиксирован без изменения scheduler flags.

### Миграции и совместимость

SQL migrations отсутствуют. Env schema не меняется. Docker Compose contract, Hermes data ownership, systemd units и reconcile protocol совместимы с текущим production runtime.

Изменение затрагивает только installer acceptance command и не требует нового application schema/data migration.

### Проверки

На initial PR head `505e02ec2d6db55e97338bd7bf0476ccb648dd91`:

- `tests`: success;
- `type check`: success;
- `docker build`: success;
- `hermes reconcile`: success;
- `branch protection contract`: success;
- `project notes contract`: initial failure только из-за формата этого worklog; содержательный кодовый check не падал;
- `security supply chain`: ещё выполнялся на момент записи.

После этого worklog приведён к обязательному project-notes contract и protected CI должен повторно пройти на новом exact head.

### PR и commit

- PR: `#716` — `Fix Hermes reconcile installer UID verification`.
- Ветка: `fix/hermes-reconcile-exec-user`.
- Базовый commit: `8b160db820592c36f51da491b0525754f6954bdf`.
- Initial PR head: `505e02ec2d6db55e97338bd7bf0476ccb648dd91`.
- Финальный head и squash merge SHA будут зафиксированы GitHub после terminal success CI.

### Незавершённое

- Protected CI должен завершиться на exact head после worklog-format fix.
- PR ещё не merged.
- Production full-archive backfill ещё не включён; scheduler flags остаются false.

### Следующий шаг

Дождаться terminal success required CI на exact PR head, выполнить squash merge #716 без обхода branch protection. Production затем может использовать уже установленный functional reconcile bridge для `submit librarian`, после успешного reconcile включить `sudo bash deploy/hermes-librarian/enable_full_archive.sh` и проверить `AUTO_ENQUEUE=true`, `AUTO_BACKFILL=true`, local Ollama route, batch `1` и фактический queue progress.
