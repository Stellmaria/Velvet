# Сессия: Arthur production reconcile-only continuation

- Дата: 2026-08-07
- ID: `2026-08-07-arthur-production-reconcile-continuation`
- Линия/фаза: Arthur Librarian Phase 2 / production acceptance (#586)
- Статус: частично
- Ветка: `ops/arthur-reconcile-continuation`
- Базовый commit: `0cf0cc814db9aed356267c7df8a08cace3cf6e79`
- PR: pending

## Перед началом

### Цель

Продолжить production acceptance с места успешного application deploy run `31195032933`, не повторяя server deploy без причины: выполнить уже установленным canonical fixed-target reconcile service target `librarian`, восстановить Git-index ownership после root reconcile при необходимости и пройти полный automated Arthur runtime gate.

### Исходный контекст

Rollout run `31195032933` успешно:

- исправил ранее подтверждённый ownership drift `.git/index` без изменения mode;
- выполнил canonical `deploy/server/deploy.sh`;
- создал и проверил pre-deploy PostgreSQL backup (`migrations=92`, `tables=105`, `characters=96`);
- развернул verified application source `e6571062af2c963297c17f94685490fa054c90ca` через exact immutable image `ghcr.io/stellmaria/velvet@sha256:517165ef91701ec7138ddb11a0138e6a2375d22a3a7683737b15ef7ea46c98d0`;
- прошёл server smoke и подтвердил healthy main bot на exact image;
- после deploy success атомарно закрепил `VELVET_IMAGE` в `.env.server` на тот же immutable digest;
- восстановил production checkout на rollout merge SHA `0cf0cc814db9aed356267c7df8a08cace3cf6e79`.

Run остановился только на попытке `sudo -n /usr/bin/bash deploy/hermes-reconcile/install.sh`: production sudo policy требует пароль. Поэтому новый merged no-optional-locks entrypoint из PR #684 пока не активирован на host. Fixed-target reconcile в run `31195032933` не запускался.

При этом canonical reconciler уже установлен и ранее принимал `reconcilectl submit librarian` (run `31191020196`). Основной blocker того reconcile — stale `velvet-bot:local` для Arthur gateway — теперь устранён persisted immutable `VELVET_IMAGE` pin из successful run `31195032933`.

### Планируемый объём

- не запускать `deploy/server/deploy.sh` повторно;
- проверить current `main`, verified source lineage и immutable digest;
- на production синхронизировать checkout deploy-user’ом на exact continuation merge SHA с `umask 022`;
- подтвердить persisted `.env.server VELVET_IMAGE == IMAGE_DIGEST` без вывода env/secrets;
- подтвердить `STORAGE_LIBRARIAN_AUTO_ENQUEUE=false`;
- подтвердить healthy main bot и exact immutable application image как deployment evidence run `31195032933`;
- использовать уже установленный `/opt/data/tools/reconcilectl.py` и fixed target `librarian` без sudo installer;
- дождаться terminal reconcile status;
- независимо от reconcile outcome восстановить owner/group только `.git/index`, если root bridge его изменит; mode не менять;
- принимать reconcile только при `status=completed`;
- после completed проверить four-service Arthur stack, exact gateway/Arthur image, отсутствие published host ports, heartbeat, manual-only queue mode, text Ollama model и Telegram `getMe`;
- сохранить clean checkout и deploy ownership `.git/index` как final evidence.

### Критерии готовности

- protected CI continuation PR полностью зелёный;
- current `main` перед merge не содержит новых application-image changes без нового publish evidence;
- workflow не выполняет повторный server deploy;
- fixed-target `reconcilectl submit librarian` принят и wait завершается `completed`;
- root reconcile не оставляет production checkout недоступным deploy user: `.git/index` после cleanup принадлежит deploy UID/GID и `GIT_OPTIONAL_LOCKS=0 git status` clean;
- `ollama-librarian`, `librarian-hermes`, `arthur-storage-gateway`, `arthur` healthy/running;
- gateway/Arthur используют exact verified immutable image;
- нет published host ports;
- `/tmp/arthur-heartbeat` существует;
- `STORAGE_LIBRARIAN_AUTO_ENQUEUE=false`;
- `ollama show velvet-librarian-text:v1` успешен;
- Telegram `getMe` успешен;
- final checkout равен exact continuation merge SHA;
- workflow печатает final `Arthur reconcile continuation verified ...` marker.

### Риски и ограничения

Installed reconcile host bridge всё ещё является pre-#684 version и может выполнить optional Git index refresh от root. Continuation не скрывает этот debt: после reconcile используется узкий bounded repair только `.git/index` owner/group с exact verified image, `--network none`, CAP_CHOWN и bind только `.git`. Durable #684 code остаётся merged, но production activation должна быть вынесена в отдельную controlled operation, если текущая sudo policy не предоставляет канонический root activation path.

Continuation не использует arbitrary root commands, новый sudo scope или альтернативный deploy. Vision/VLM не меняется и остаётся #630. Mass/AFK enqueue, archive backfill и cloud/provider execution не вводятся.

## После завершения

### Фактически сделано

Добавлен `.github/workflows/arthur-production-reconcile-continuation.yml`. Workflow использует общую `velvet-production` concurrency group, full-history checkout и production deploy SSH credentials. Arthur bot/gateway secrets повторно в workflow не передаются.

Remote continuation сначала синхронизирует production checkout на exact merge SHA, проверяет immutable env pin/manual-only mode и healthy core bot exact image. Затем submit/wait выполняются через уже установленный `reconcilectl.py` только для fixed target `librarian`.

Добавлен EXIT cleanup для `.git/index`: после начала reconcile owner/group index при необходимости возвращаются deploy user через transient verified-image container без сети и без изменения mode. Completed reconcile затем открывает существующие Arthur runtime gates.

### Миграции и совместимость

SQL/application migrations отсутствуют. Application image не пересобирается и server deployment не повторяется. Verified application source/image pair остаётся source `e6571062...`, digest `sha256:517165...`, publish run `31179477871`.

### Проверки

Production continuation ещё не выполнялся. До merge требуется полный protected CI и повторная current-main provenance проверка.

### PR и commit

- Ветка: `ops/arthur-reconcile-continuation`.
- База: `0cf0cc814db9aed356267c7df8a08cace3cf6e79`.
- Workflow commit: `0b8550d61800d1c2bb3552740acc12528031d193`.

### Незавершённое

- открыть continuation PR и пройти protected CI;
- проверить current `main` перед merge;
- выполнить fixed-target production reconcile continuation;
- при automated success выполнить manual live acceptance #586: Telegram commands, safe analyze/result, PostgreSQL persisted evidence, ask/digest/queue/download, main-bot command isolation, zero-provider evidence, latency/resources и restart/reconcile persistence;
- создать отдельный controlled ops issue для production activation merged #684 no-optional-locks reconcile entrypoint, если canonical activation по текущей sudo policy остаётся недоступной;
- только после полного acceptance обновить/закрыть #586.

### Следующий шаг

Открыть reconcile-only continuation PR, дождаться полностью зелёного CI и merge только при сохранённой application provenance; затем принять production continuation исключительно при `completed` reconcile, healthy Arthur stack, clean/deploy-owned Git index и final verification marker.
