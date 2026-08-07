# Сессия: Arthur production rollout run 7 и verified image wiring

- Дата: 2026-08-07
- ID: `2026-08-07-arthur-production-rollout-run7`
- Линия/фаза: Arthur Librarian Phase 2 / production acceptance (#586)
- Статус: частично
- Ветка: `ops/arthur-rollout-pin-verified-image`
- Базовый commit: `88326f61e42b97bdb4df56001436fcf46bb6cb2d`
- PR: pending

## Перед началом

### Цель

Устранить подтверждённый production blocker Arthur Storage gateway: fixed-target Librarian reconcile должен запускать Arthur/gateway на том же verified immutable Velvet image, который успешно использовал canonical server deploy, а не на stale `velvet-bot:local` из `.env.server`.

### Исходный контекст

Rollout run `31191020196` подтвердил исправление stdin boundary: canonical `deploy/server/deploy.sh` успешно развернул verified application source `e6571062af2c963297c17f94685490fa054c90ca` через immutable image `ghcr.io/stellmaria/velvet@sha256:517165ef91701ec7138ddb11a0138e6a2375d22a3a7683737b15ef7ea46c98d0`, затем checkout был восстановлен на rollout SHA `558f846040fed92ac3935f2fce2dcbd52a284946` и fixed-target Librarian reconcile task `reconcile_ef81a87a43e243a1b6fba648a518598c` был принят.

Reconcile завершился `failed` при запуске `velvet-librarian.service`. Read-only diagnostics run `31192193835` затем установил точную причину: `ollama-librarian` и `librarian-hermes` healthy, обе локальные model aliases присутствуют, но `arthur-storage-gateway` циклически рестартует с `python: can't open file '/app/scripts/run_arthur_storage_gateway.py'`. Compose запустил gateway на `velvet-bot:local`; stale local image не содержит Phase 2 runtime script. Arthur не стартовал.

Canonical `deploy/server/deploy.sh` корректно принимает `VELVET_DEPLOY_IMAGE` и временно экспортирует `VELVET_IMAGE` только внутри процесса deploy. Fixed reconcile/systemd запускаются отдельным процессом и снова читают persisted `.env.server`, где остаётся local tag. Это и создаёт drift между основным bot deploy и Arthur profile.

### Планируемый объём

- сохранить verified application source/image pair без изменений;
- не менять canonical server deploy или fixed-target reconcile path;
- после успешного canonical deploy атомарно закрепить `VELVET_IMAGE` в `.env.server` на exact `IMAGE_DIGEST` rollout;
- не выполнять pin до deploy success, чтобы не влиять на server rollback при неуспешном deploy;
- валидировать только immutable `ghcr.io/stellmaria/velvet@sha256:<64 hex>`;
- после reconcile проверить, что `arthur-storage-gateway` и `arthur` реально запущены именно с этим exact digest;
- сохранить существующие health/no-ports/heartbeat/manual-only/Ollama/getMe gates;
- не включать mass enqueue и не расширять vision scope.

### Критерии готовности

- protected CI нового rollout PR полностью зелёный;
- current `main` перед merge не содержит application-image changes без нового publish evidence;
- canonical deploy завершается успешно с verified source/image pair;
- persisted `VELVET_IMAGE` закреплён только после deploy success;
- Librarian reconcile task завершается `completed`;
- `ollama-librarian`, `librarian-hermes`, `arthur-storage-gateway`, `arthur` healthy/running;
- Arthur/gateway используют exact verified immutable image;
- нет published host ports;
- heartbeat существует, `STORAGE_LIBRARIAN_AUTO_ENQUEUE=false`, text model доступна, Telegram `getMe` успешен;
- job содержит финальный `Arthur production rollout verified ...` marker.

### Риски и ограничения

Изменение `.env.server` является production configuration mutation, поэтому оно выполняется только после успешного canonical deploy и атомарной записью mode `0600`. Значение pin не является secret, но workflow всё равно не выводит содержимое env. Vision model/runtime не меняются: #630 остаётся единственным владельцем VLM scope. Никаких mass/AFK enqueue, archive backfill, cloud/provider execution или альтернативного deploy path.

## После завершения

### Фактически сделано

В `.github/ops/arthur-production-rollout.sh` добавлен post-deploy image pin: после успешного `deploy/server/deploy.sh` bridge проверяет strict immutable GHCR format и атомарно обновляет только `VELVET_IMAGE` в `.env.server` на rollout `IMAGE_DIGEST`.

После fixed-target reconcile существующий health loop дополнен exact runtime image assertion для `arthur-storage-gateway` и `arthur`: `.Config.Image` контейнеров обязан совпадать с `IMAGE_DIGEST`.

Rollout workflow получил bounded revision marker `pin-verified-arthur-image`, чтобы merge этого PR снова запустил одноразовый rollout. `SOURCE_COMMIT` и `IMAGE_DIGEST` не менялись.

### Миграции и совместимость

SQL/application migrations отсутствуют. Изменение не требует нового application image и не меняет application source. `.env.server` получает immutable image pin, совместимый с существующим `${VELVET_IMAGE:-velvet-bot:local}` contract в Librarian Compose и с основным server Compose.

### Проверки

Read-only diagnostics run `31192193835` является source evidence для remediation: gateway failure связан именно со stale local image; Ollama/Hermes уже healthy, `velvet-librarian-text:v1` и `velvet-librarian-vision:v1` существуют. Наличие vision alias не считается acceptance #586 и не расширяет scope.

Protected CI и следующий production rollout ещё должны завершиться. До merge требуется повторно проверить current `main` и provenance.

### PR и commit

- Ветка: `ops/arthur-rollout-pin-verified-image`.
- База: `88326f61e42b97bdb4df56001436fcf46bb6cb2d`.
- Bridge change commit: `e75cbdfd1dbd0c7ec7a198a4162e20a6bac3dbdf`.
- Workflow trigger commit: `6d96c96c8845b8cdc15ab17d0a2f3687891b46be`.
- Verified application source: `e6571062af2c963297c17f94685490fa054c90ca`.
- Verified image digest: `sha256:517165ef91701ec7138ddb11a0138e6a2375d22a3a7683737b15ef7ea46c98d0`.

### Незавершённое

- открыть PR и пройти protected CI;
- проверить current `main` перед merge;
- выполнить rollout и получить completed Librarian reconcile/final automated Arthur marker;
- после automated acceptance выполнить manual live Telegram/storage/answer workflow, persisted PostgreSQL evidence, zero-provider checks, resource/latency measurement и restart/reconcile persistence;
- только после полного evidence обновить и закрыть #586.

### Следующий шаг

Открыть bounded rollout PR, дождаться полностью зелёного protected CI и merge только при сохранённой application provenance; затем разобрать production run до exact final checkout/reconcile/runtime-image/health evidence.
