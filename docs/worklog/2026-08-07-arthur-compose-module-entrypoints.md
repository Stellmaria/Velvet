# Сессия: Arthur Compose Python module entrypoints

- Дата: 2026-08-07
- ID: `2026-08-07-arthur-compose-module-entrypoints`
- Линия/фаза: Arthur Librarian Phase 2 / production acceptance (#586)
- Статус: частично
- Ветка: `fix/arthur-compose-module-entrypoints`
- Базовый commit: `5ac855f30476346abd4df2ccb8e5fcff27a3ce56`
- PR: pending

## Перед началом

### Цель

Исправить подтверждённый production import-path blocker Arthur Storage gateway и симметричный latent blocker основного Arthur runtime без пересборки application image.

### Исходный контекст

Reconcile-only run `31195796153` подтвердил persisted immutable `VELVET_IMAGE`, manual-only queue mode и healthy core bot, но fixed-target Librarian reconcile `reconcile_20e0b7deb8924f1ab065eb88d4fa313d` завершился `failed` на `velvet-librarian.service`.

Read-only diagnostics run `31196392481` установил точную причину текущего failure:

- `arthur-storage-gateway` действительно запущен с exact verified image `ghcr.io/stellmaria/velvet@sha256:517165ef91701ec7138ddb11a0138e6a2375d22a3a7683737b15ef7ea46c98d0`;
- script `/app/scripts/run_arthur_storage_gateway.py` в image присутствует;
- container падает с `ModuleNotFoundError: No module named 'velvet_bot'`;
- `arthur` ещё не запускается, потому что depends on healthy gateway;
- `ollama-librarian` и `librarian-hermes` healthy;
- production checkout clean, `.git/index` возвращён deploy user, immutable image pin match, `STORAGE_LIBRARIAN_AUTO_ENQUEUE=false`.

Dockerfile verified image использует `WORKDIR /app` и `COPY . .`. Librarian Compose при этом запускает gateway как `python scripts/run_arthur_storage_gateway.py`. При direct script execution Python выставляет import search root на `/app/scripts`, поэтому sibling top-level package `/app/velvet_bot` не разрешается. Arthur использует такой же direct-script command и имеет тот же latent defect.

### Планируемый объём

- не менять Dockerfile, `scripts/*.py` или `velvet_bot/**`;
- не пересобирать verified application image;
- изменить только commands Arthur profile в `deploy/hermes-librarian/compose.yaml` на module execution из image `WORKDIR=/app`;
- gateway: `python -m scripts.run_arthur_storage_gateway`;
- Arthur: `python -m scripts.run_arthur_librarian`;
- добавить regression test exact Compose commands и Python module resolvability;
- сохранить exact verified image digest, private network/no published ports, owner-only credentials, manual-only queue mode и весь существующий runtime security contract;
- не включать vision implementation или mass enqueue.

### Критерии готовности

- protected CI полностью зелёный;
- test фиксирует module execution для обоих Arthur services;
- current `main` перед merge не содержит новых application-image changes без нового publish evidence;
- merge не требует нового image digest, потому что runtime code уже присутствует в immutable image и меняется только host Compose command;
- subsequent fixed-target reconcile запускает gateway на exact verified digest без `ModuleNotFoundError`;
- Arthur затем достигает heartbeat и остальные automated gates.

### Риски и ограничения

Изменение Compose является production runtime wiring change, но не изменяет содержимое image. Оно полагается на уже подтверждённый `WORKDIR /app` immutable image. Python `-m` намеренно используется вместо глобального `PYTHONPATH`, чтобы не расширять import surface всего контейнера сверх обычного module execution из working directory.

Vision/VLM implementation остаётся #630. Наличие vision model alias в Ollama не является acceptance #586. `STORAGE_LIBRARIAN_AUTO_ENQUEUE=false` остаётся обязательным.

## После завершения

### Фактически сделано

`deploy/hermes-librarian/compose.yaml` переведён с direct script execution на Python module execution для `arthur-storage-gateway` и `arthur`. Image, user, capabilities, read-only rootfs, tmpfs, networks, healthchecks и resource limits не менялись.

Добавлен `tests/test_arthur_compose_entrypoints.py`, который проверяет exact commands и разрешимость `scripts.run_arthur_storage_gateway`, `scripts.run_arthur_librarian` и `velvet_bot` из repository root, соответствующего Docker `WORKDIR /app`.

### Миграции и совместимость

SQL/application migrations отсутствуют. Dockerfile/application package не меняются. Verified source/image provenance остаётся source `e6571062af2c963297c17f94685490fa054c90ca`, digest `sha256:517165ef91701ec7138ddb11a0138e6a2375d22a3a7683737b15ef7ea46c98d0`, publish run `31179477871`, если current-main provenance check перед merge не обнаружит новый image-build-path commit.

### Проверки

Production diagnostics run `31196392481` является direct evidence blocker. Protected CI этой ветки и следующий production reconcile ещё не завершены.

### PR и commit

- Ветка: `fix/arthur-compose-module-entrypoints`.
- База: `5ac855f30476346abd4df2ccb8e5fcff27a3ce56`.
- Compose fix commit: `ed9969acbfc380d498d175d112413843142c5edc`.
- Regression test commit: `4dce4f072fbb43577a0caf0b213181626ad96c4a`.

### Незавершённое

- открыть PR и пройти protected CI;
- повторно проверить current `main` / application provenance;
- после merge выполнить reconcile-only continuation без server redeploy;
- получить completed reconcile и full automated Arthur gates;
- затем выполнить manual live acceptance #586 и оформить remaining host reconcile activation debt #684 отдельно, если требуется.

### Следующий шаг

Открыть bounded runtime-wiring PR, дождаться полностью зелёного CI и затем повторить fixed-target reconcile-only continuation на прежнем verified immutable image.
