# Сессия: hotfix server deploy Compose race и rollback image

- Дата: 2026-08-05
- ID: `server-deploy-compose-race-hotfix-20260805`
- Линия/фаза: production deployment safety
- Статус: `завершено`
- Ветка: `fix/deploy-compose-race-rollback`
- Базовый commit: `73f7ef51d51f10cb2c8cd5181c9da74465864207`
- Связанное issue: `#586`

## Перед началом

### Цель

Исправить подтверждённый production-сбой `opsctl velvet update`: Docker Compose пересоздал зависимости и затем попытался стартовать уже удалённый bot container ID. Одновременно rollback ошибочно выполнял `docker pull velvet-bot:local`, хотя локальный тег не является registry reference и уже мог быть перезаписан новой сборкой.

### Планируемый объём

- запускать PostgreSQL и Supervisor proxy отдельно от bot;
- дождаться health зависимостей до пересоздания bot;
- запускать bot через отдельный `--no-deps` шаг;
- сохранить точный image ID работающего bot под отдельным rollback-тегом;
- не выполнять pull локального rollback image;
- проверять health и server smoke после отката;
- добавить regression-контракты и shell validation.

### Критерии готовности

- combined `compose up` больше не пересоздаёт зависимости и bot одной операцией;
- rollback использует сохранённый image ID, а не перезаписанный логический тег;
- registry pull разрешён только для immutable GHCR digest;
- rollback сообщает отдельную ошибку, если healthy runtime не восстановлен;
- `bash -n`, focused tests и обязательный CI проходят.

## После завершения

### Фактически сделано

- добавлены `start_core_services`, `start_bot_service` и bounded health waits;
- bot удаляется и создаётся отдельным Compose шагом с `--no-deps` после healthy PostgreSQL и Supervisor proxy;
- точный image ID текущего bot сохраняется под `velvet-bot:rollback-<sha>` до новой сборки;
- локальный rollback image больше не передаётся в `docker pull`;
- immutable GHCR digest остаётся единственным допустимым pull fallback;
- rollback отключает рекурсивный trap, проверяет bot health и выполняет `server_smoke.py`;
- успешный deploy удаляет временный rollback-тег;
- обновлены server supervisor regression contracts.

### Проверки

- `bash -n deploy/server/deploy.sh`;
- `python -m unittest tests.test_server_supervisor_contract`;
- полный required CI PR.

### Незавершённое

После merge требуется повторный `opsctl velvet update`, затем `reconcilectl submit librarian` и manual smoke Storage #2168 при выключенном auto enqueue.
