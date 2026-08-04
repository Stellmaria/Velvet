# Сессия: hotfix server deploy Compose race и rollback image

- Дата: 2026-08-05
- ID: `server-deploy-compose-race-hotfix-20260805`
- Линия/фаза: production deployment safety
- Статус: `завершено`
- Ветка: `fix/deploy-compose-race-rollback-v2`
- Базовый commit: `73f7ef51d51f10cb2c8cd5181c9da74465864207`
- Связанное issue: `#586`

## Перед началом

### Цель

Исправить подтверждённый production-сбой `opsctl velvet update`: Docker Compose пересоздал зависимости и затем попытался стартовать уже удалённый bot container ID. Одновременно rollback ошибочно выполнял `docker pull velvet-bot:local`, хотя локальный тег не является registry reference и уже мог быть перезаписан новой сборкой.

### Исходный контекст

При rollout Phase 1 Артура target commit успешно fetched, checkout переключился на новый `main`, PostgreSQL dump прошёл верификацию, а bot image собрался. Сбой произошёл на этапе совместного `compose up` для PostgreSQL, Supervisor proxy и bot: Docker daemon получил ссылку на уже удалённый container ID. Защитный rollback вернул код на предыдущий commit, но попытался подтянуть локальный mutable tag из registry. Рабочий production bot остался healthy, база не восстанавливалась и verified dump сохранился.

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

### Риски и ограничения

Hotfix изменяет общий production deploy-контур, поэтому ошибочная последовательность может повлиять не только на Librarian rollout. Изменения ограничены запуском core-сервисов, bot и rollback path; миграции, production env, database restore и automatic archive enqueue не затрагиваются. Реальный Docker race нельзя полноценно воспроизвести unit-тестом, поэтому после merge обязателен контролируемый повторный rollout с наблюдением terminal status и bot health.

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

### Миграции и совместимость

SQL-миграции отсутствуют. Формат `.env.server`, Compose service names и Supervisor API не меняются. Verified GHCR deployment остаётся совместимым: immutable digest по-прежнему загружается и сверяется с target SHA. Local-build fallback сохраняется, но rollback теперь привязан к точному image ID прежнего работающего контейнера.

### Проверки

- `bash -n deploy/server/deploy.sh`;
- `python -m unittest tests.test_server_supervisor_contract`;
- полный required CI PR.

### PR и commit

Рабочий PR: `#627`. Чистый reviewed head до worklog completion: `532cb576f2244460b0b52991fcdf97ab01b797d4`. Draft PR `#625` закрыт без merge как дубликат с техническими промежуточными commit.

### Незавершённое

После merge требуется повторный `opsctl velvet update`, затем `reconcilectl submit librarian` и manual smoke Storage #2168 при выключенном auto enqueue.

### Следующий шаг

Дождаться полного зелёного required CI на финальном head PR #627, перевести PR в ready и выполнить squash merge. После merge повторить production update через существующий `velvet-hermes-1`, подтвердить deployed SHA и healthy bot, затем выполнить Librarian reconcile и один ручной smoke-тест.
