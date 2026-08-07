# Сессия: Arthur reconcile после module-entrypoint fix

- Дата: 2026-08-07
- ID: `2026-08-07-arthur-reconcile-module-entrypoints`
- Линия/фаза: Arthur Librarian Phase 2 / production acceptance (#586)
- Статус: частично
- Ветка: `ops/arthur-reconcile-module-entrypoints`
- Базовый commit: `63116d2b9b902eb82c4b1bca3bb9b34df52d7f3a`
- PR: pending

## Перед началом

### Цель

Повторить только fixed-target Librarian reconcile после merge #688, который исправил подтверждённый Python import-path blocker Arthur gateway/Arthur через module execution, без повторного server deploy и без изменения verified immutable image.

### Исходный контекст

Production application deployment run `31195032933` уже успешно развернул source `e6571062af2c963297c17f94685490fa054c90ca` на image `ghcr.io/stellmaria/velvet@sha256:517165ef91701ec7138ddb11a0138e6a2375d22a3a7683737b15ef7ea46c98d0`, прошёл server smoke и закрепил persisted `VELVET_IMAGE` на тот же digest.

Reconcile continuation `31195796153` затем подтвердил immutable image pin, manual-only queue mode и healthy main bot, но task `reconcile_20e0b7deb8924f1ab065eb88d4fa313d` упал на `velvet-librarian.service`. Fresh diagnostics `31196392481` установил exact blocker: gateway уже использовал правильный digest и script существовал, но direct invocation `python scripts/run_arthur_storage_gateway.py` падал с `ModuleNotFoundError: No module named 'velvet_bot'`.

PR #688 merged как `63116d2b9b902eb82c4b1bca3bb9b34df52d7f3a` и меняет только host Compose commands на `python -m scripts.run_arthur_storage_gateway` и `python -m scripts.run_arthur_librarian`. Dockerfile/application code не менялись, production image security CI подтвердил unchanged image surface.

### Планируемый объём

- изменить только revision marker существующего reconcile-only workflow для нового push trigger;
- не запускать `deploy/server/deploy.sh`;
- синхронизировать production checkout на exact retry merge SHA;
- сохранить source/digest pair без изменений;
- выполнить installed fixed-target `reconcilectl submit librarian`/wait;
- сохранить existing Git-index cleanup after root reconcile;
- принимать только `status=completed`;
- затем проверить четыре Arthur services, exact gateway/Arthur image, no published ports, heartbeat, `STORAGE_LIBRARIAN_AUTO_ENQUEUE=false`, text Ollama model и Telegram `getMe`.

### Критерии готовности

- protected CI retry PR зелёный;
- current `main` перед merge не содержит новых application-image changes;
- reconcile завершается `completed`;
- gateway больше не имеет `ModuleNotFoundError`;
- Arthur достигает healthy/running и heartbeat;
- final automated verification marker присутствует;
- #586 остаётся открытой до manual live acceptance.

### Риски и ограничения

Installed reconcile host bridge всё ещё pre-#684 и может refresh-нуть Git index от root; continuation сохраняет bounded owner/group cleanup только `.git/index`. Этот host activation debt не скрывается и должен остаться отдельной controlled operation. Vision/VLM остаётся #630. Mass/AFK enqueue, archive backfill и cloud/provider execution не вводятся.

## После завершения

### Фактически сделано

В `.github/workflows/arthur-production-reconcile-continuation.yml` добавлен только `CONTINUATION_REVISION=module-entrypoints-v1`, чтобы merge повторно запустил уже существующую reconcile-only логику на checkout, содержащем #688. Остальная production continuation логика не менялась.

### Миграции и совместимость

SQL/application migrations отсутствуют. Server deploy не повторяется. Verified application source/image pair остаётся прежней.

### Проверки

Production run ещё не запущен. До merge требуется полный protected CI и current-main provenance check.

### PR и commit

- Ветка: `ops/arthur-reconcile-module-entrypoints`.
- База: `63116d2b9b902eb82c4b1bca3bb9b34df52d7f3a`.
- Workflow retry commit: `043f8a395e1250be5a66c476f6c82b8905a208da`.

### Незавершённое

- открыть PR и пройти protected CI;
- merge при сохранённой provenance;
- разобрать reconcile task и automated Arthur gates;
- при automated success выполнить manual live Telegram/storage/answer acceptance #586.

### Следующий шаг

Запустить reconcile-only continuation через merge этого bounded retry PR и принять результат только при `completed` task и полном Arthur verification marker.
