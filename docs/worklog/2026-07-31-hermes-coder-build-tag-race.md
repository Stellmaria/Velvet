# 2026-07-31 — Устранение гонки тегов сборки Hermes Coder

- Дата: `2026-07-31`
- ID: `hermes-coder-build-tag-race`
- Линия/фаза: `server operations`
- Статус: `завершено`
- Ветка: `fix/hermes-coder-build-tag-race`
- Базовый commit: `1d7c303bf096378e112dbeaa90ba73da5daaf9c8`

## Перед началом

### Цель

Устранить падение production installer при параллельной сборке двух Hermes Coder и двух DB-proxy сервисов через Docker Compose.

### Исходный контекст

Повторный запуск installer успешно переиспользовал отдельные checkout Velvet и Max и дошёл до `docker compose build`. Оба coder-сервиса наследовали один и тот же `image: velvet-hermes-coder:local`, а оба proxy-сервиса один и тот же `image: velvet-hermes-db-proxy:local`.

BuildKit начал собирать сервисы параллельно. Один coder успел опубликовать manifest под общим тегом, второй завершился ошибкой:

```text
failed to solve: image "docker.io/library/velvet-hermes-coder:local": already exists
```

Из-за `set -e` installer остановился и SSH-сессия закрылась. Gateway не запускались, production-боты и PostgreSQL не затрагивались.

### Планируемый объём

- сохранить общий Dockerfile и одинаковые слои образов;
- назначить каждому Compose-сервису уникальный локальный image tag;
- устранить аналогичную потенциальную гонку DB-proxy;
- сохранить независимую сборку profile `velvet` и profile `max`;
- добавить regression-контракт.

### Критерии готовности

- `hermes-coder-velvet` и `hermes-coder-max` не экспортируют один тег;
- `velvet-db-proxy` и `max-db-proxy` не экспортируют один тег;
- оба profile можно собирать одновременно;
- слои Docker продолжают дедуплицироваться локальным content store;
- сетевые, mount и credential-границы не меняются;
- обязательный Docker CI проходит реальную сборку всех четырёх сервисов.

### Риски и ограничения

Docker будет хранить четыре manifest tag вместо двух, но одинаковые слои не дублируются физически. Старые локальные теги могут остаться на VPS как неиспользуемые образы; их удаление не требуется для завершения установки и не выполняется автоматически.

## После завершения

### Фактически сделано

В `deploy/hermes-coders/compose.yaml` общие `image` удалены из YAML anchors и заданы отдельно для сервисов:

```text
velvet-hermes-coder-velvet:local
velvet-hermes-coder-max:local
velvet-hermes-db-proxy-velvet:local
velvet-hermes-db-proxy-max:local
```

Общие build context и Dockerfile сохранены. Таким образом Compose может собирать оба profile параллельно, не пытаясь одновременно записать один manifest tag.

### Миграции и совместимость

SQL-миграций нет. Production Compose Velvet и Max, PostgreSQL, Hermes Operator, read-only роли, workspaces и secrets не меняются. Повторный installer продолжает с уже созданного состояния.

### Проверки

В `tests/test_hermes_coders_contract.py` добавлен контракт, который:

- требует четыре уникальных image tag;
- проверяет наличие каждого тега ровно один раз;
- запрещает возврат общих конфликтующих тегов.

Обязательные проверки PR:

- project notes contract;
- type check;
- unit tests;
- Docker build с одновременной сборкой обоих profiles.

### PR и commit

- Ветка: `fix/hermes-coder-build-tag-race`
- Основные commits: `ea4581e82f7ae796bec8e7a0913eac2bf3b3c6b0`, `b0eab366c6e7b1070b369b8476872d7a928e5ec6`

### Незавершённое

После merge требуется обновить `/srv/velvet`, повторно запустить installer и убедиться, что он завершает build, устанавливает systemd unit и оставляет gateway inactive до заполнения credentials.

### Следующий шаг

Открыть PR, дождаться зелёного Docker CI, слить исправление и повторить безопасный installer на VPS без запуска gateway.
