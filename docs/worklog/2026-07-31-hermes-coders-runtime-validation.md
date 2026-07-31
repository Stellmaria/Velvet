# 2026-07-31 — Runtime-проверка образов Hermes Coder

- Дата: `2026-07-31`
- ID: `hermes-coders-runtime-validation`
- Линия/фаза: `server operations`
- Статус: `завершено`
- Ветка: `ci/hermes-coders-runtime-validation`
- Базовый commit: `a6f54ebf327b566a6bcaae69a3c5740d72cd10a0`

## Перед началом

### Цель

Закрепить в обязательном Docker CI реальную проверку Compose-конфигурации и сборки обоих новых образов Hermes Coder до установки стека на VPS.

### Исходный контекст

PR `#500` добавил изолированный стек Hermes Coder и прошёл существующие проверки. Однако текущий workflow собирал только основные образы Velvet, Server Supervisor proxy и Krita. Новый `Dockerfile.coder`, `Dockerfile.db-proxy` и отдельный `compose.yaml` попадали под path trigger, но не выполнялись в job, поэтому зелёный Docker check не доказывал их фактическую собираемость.

### Планируемый объём

- подготовить в CI временные env, data и workspace paths для обоих кодеров;
- проверить Bash и Python-файлы Hermes Coder;
- выполнить `docker compose config --quiet` для обоих profiles;
- собрать derived Hermes Coder image и DB-proxy image;
- не запускать gateway и не использовать реальные credentials.

### Критерии готовности

- Compose-конфигурация обоих profiles проходит на чистом runner;
- `install.sh`, `db_proxy.py` и `preflight.py` синтаксически корректны;
- оба Dockerfile реально собираются из зафиксированных base images;
- в CI используются только тестовые credentials и временный каталог `.ci/hermes-coders`;
- существующие Docker и Krita проверки сохраняются.

### Риски и ограничения

Сборка derived Hermes image требует скачивания внешнего base image и пакетов, поэтому Docker workflow станет немного длиннее. Gateway намеренно не запускается в CI, поскольку для полноценного smoke потребовались бы Telegram и Byesu credentials, которые нельзя передавать в pull request job.

## После завершения

### Фактически сделано

Workflow `.github/workflows/docker-build.yml` дополнен этапами:

- `Prepare Hermes Coder compose environment`;
- Bash-проверка `deploy/hermes-coders/install.sh`;
- Python compile для `db_proxy.py` и `preflight.py`;
- Compose validation стека с profiles `velvet` и `max`;
- `Build Hermes Coder images` через отдельный compose-файл.

Тестовые env-файлы создаются только внутри `.ci/hermes-coders` на GitHub runner и не содержат production secrets.

### Миграции и совместимость

SQL-миграций и runtime-изменений нет. Production Compose, systemd и работающие контейнеры не меняются. Изменяется только обязательный CI workflow.

### Проверки

После публикации ветки должны пройти:

- project notes contract;
- type check;
- unit tests;
- Docker build, включая новые coder и DB-proxy images.

### PR и commit

- Ветка: `ci/hermes-coders-runtime-validation`
- Основной commit: `5c23f653984039be3ebef445eb9b29afe70833fe`
- Follow-up PR создаётся в `main` после добавления worklog.

### Незавершённое

До установки на VPS остаётся дождаться зелёного Docker build, слить follow-up PR и только затем обновлять `/srv/velvet` и запускать installer без старта gateway.

### Следующий шаг

Открыть follow-up PR, проверить фактические логи сборки новых образов, исправить несовместимость base image или Compose при её обнаружении и слить изменения только после зелёного CI.
