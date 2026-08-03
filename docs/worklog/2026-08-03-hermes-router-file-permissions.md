# Сессия: права Python-файлов в образе Hermes coder-router

- Дата: 2026-08-03
- ID: 2026-08-03-hermes-router-file-permissions
- Линия/фаза: server operations / Hermes coder-router hotfix
- Статус: частично
- Ветка: hotfix/hermes-router-file-permissions
- Базовый commit: eac33eb8a6702d2ab6d974edb0ce00b16b4e10bd

## Перед началом

### Цель

Устранить restart loop `hermes-coder-router`, возникший при первом controlled rollout PR #574, и гарантировать читаемость Python entrypoint-файлов непривилегированным пользователем контейнера.

### Исходный контекст

Controlled rollout commit `eac33eb8a6702d2ab6d974edb0ce00b16b4e10bd` успешно поднял шесть coder-контейнеров и прошёл runtime/provider-chain smoke, включая `Mini -> Terra -> Luna`. Затем `hermes-coder-router.service` завершился ошибкой, потому что контейнер не мог прочитать `/app/coder_router.py`:

`python: can't open file '/app/coder_router.py': [Errno 13] Permission denied`

Автоматический rollback вернул production на `798e959b1f0cde636df0d97c3438f20de831b427`, восстановил прежние units и полный Hermes state. Шесть coder-контейнеров после rollback снова healthy.

### Планируемый объём

- задать явные права `0555` для `gateway.py` и `coder_router.py` на стадии Docker build;
- сохранить запуск router-контейнера под `USER 10001:10001`;
- добавить contract-тест, запрещающий обычный `COPY` без `--chmod`;
- не менять provider-chain runner, systemd lifecycle и production runtime в этом PR.

### Критерии готовности

- Dockerfile использует `COPY --chmod=0555` для обоих Python-файлов;
- contract-тест фиксирует права и непривилегированного пользователя;
- Docker build и тесты проходят;
- production не меняется до отдельного merge и повторного controlled rollout.

### Риски и ограничения

- CI проверяет структуру образа и build, но не заменяет повторный live smoke systemd/router на VPS;
- текущий production остаётся на rollback SHA до отдельного разрешения;
- restart-loop контейнер после диагностики должен быть удалён отдельно на сервере, не через этот PR.

## После завершения

### Фактически сделано

- `gateway.py` копируется в образ с mode `0555`;
- `coder_router.py` копируется в образ с mode `0555`;
- добавлен отдельный contract-тест на оба `COPY --chmod=0555` и `USER 10001:10001`;
- provider-chain и systemd-файлы не менялись.

### Миграции и совместимость

Схемы данных, API, environment и Compose contract не меняются. Изменяется только mode двух файлов внутри собираемого router-образа.

### Проверки

- contract-тест добавлен;
- GitHub CI будет запущен после открытия draft PR;
- повторный live router smoke не выполнялся и остаётся обязательным после merge.

### PR и commit

- ветка: `hotfix/hermes-router-file-permissions`;
- базовый commit: `eac33eb8a6702d2ab6d974edb0ce00b16b4e10bd`;
- draft PR будет создан после публикации изменений;
- merge и deployment не выполнялись.

### Незавершённое

- дождаться полного CI;
- выполнить review и merge;
- повторить controlled rollout на VPS;
- подтвердить active `hermes-coder-router.service`, running/healthy container, `router_smoke.py` и Telegram handoff.

### Rollback

Вернуть обычные `COPY` в Dockerfile только вместе с доказанной альтернативной нормализацией прав. Production rollback продолжает использовать backup `/srv/hermes-coders/backups/provider-chain-predeploy-20260803T182009Z`.

### Следующий шаг

Открыть draft PR, дождаться полного зелёного CI и после отдельного разрешения выполнить merge и повторный controlled rollout с существующим автоматическим rollback.
