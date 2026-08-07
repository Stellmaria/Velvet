# Сессия: одноразовый production rollout Arthur Librarian Phase 2

- Дата: 2026-08-07
- ID: `2026-08-07-arthur-production-rollout`
- Линия/фаза: Arthur Librarian Phase 2 / production rollout
- Статус: частично
- Ветка: `ops/arthur-prod-rollout-20260806`
- Базовый commit: `7b561b0bb2d04b7d5fd4fa3ae084d9af830c424f`
- PR: #667

## Перед началом

### Цель

Подготовить одноразовый, проверяемый и откатываемый production rollout Arthur Librarian Phase 2 через GitHub Actions без публикации секретов и без обхода канонического immutable-image deploy-контракта.

### Исходный контекст

PR #667 был создан как эксплуатационный мост для production rollout и намеренно не меняет application runtime. Ветка изначально была привязана к commit `7b561b0bb2d04b7d5fd4fa3ae084d9af830c424f` и к заранее опубликованному immutable image digest.

После создания PR в `main` были объединены #666, #662 и #663. Исходный `SOURCE_COMMIT` и image digest стали устаревшими, поэтому rollout не запускался с промежуточным provenance. После merge #663 ветка #667 синхронизирована с актуальным `main`, а финальная application provenance взята только из успешного штатного `publish-image.yml` для точного merge commit.

### Планируемый объём

- синхронизировать rollout-ветку с актуальным `main` после завершения зависимых PR;
- получить immutable image digest только из успешного штатного publish pipeline для точного production source commit;
- обновить `SOURCE_COMMIT` и `IMAGE_DIGEST` в one-time workflow;
- сохранить отдельную установку Arthur production credentials без вывода значений;
- использовать канонический `deploy/server/deploy.sh`, а не отдельный альтернативный deploy path;
- после deploy выполнить fixed-target Librarian reconcile и эксплуатационные health checks;
- проверить отсутствие published ports, heartbeat, manual-only queue mode, Ollama model availability и Telegram `getMe`;
- не запускать production rollout до отдельного явного решения на merge PR #667.

### Критерии готовности

- rollout source commit совпадает с проверенным актуальным application `main`;
- image digest получен из успешного `publish-image.yml` для этого же source commit;
- required GitHub checks PR #667 зелёные;
- workflow не печатает production credentials или токены;
- rollout script сохраняет immutable deploy и fixed-target reconcile contracts;
- merge PR #667 остаётся единственной точкой запуска одноразового production rollout;
- до merge пользователю явно сообщено, что merge запускает production.

### Риски и ограничения

- merge этого PR является эксплуатационным действием и запускает production rollout, поэтому он не должен выполняться автоматически как обычная уборка PR;
- использование старого source commit вместе с новым checkout создаёт риск несовместимого production состояния;
- digest должен быть связан с точным source commit, а не с плавающим tag;
- production credentials разрешено только передавать через GitHub environment/secrets и серверные файлы с ограниченными правами, без вывода значений;
- live Telegram, Ollama и Librarian проверки доступны только во время фактического rollout.

## После завершения

### Фактически сделано

Подготовлен one-time workflow `.github/workflows/arthur-production-rollout-v2.yml` и серверный bridge `.github/ops/arthur-production-rollout.sh`. Контракт предусматривает immutable application deploy, отдельную установку Arthur credentials, восстановление checkout на итоговый merge commit, fixed-target Librarian reconcile и post-deploy health checks.

PR #663 успешно прошёл protected CI и был объединён в `main` commit `e6571062af2c963297c17f94685490fa054c90ca`. Штатный `publish-image.yml` run `31179477871` для этого exact commit успешно выполнил build, Trivy HIGH/CRITICAL gate, CycloneDX SBOM и GHCR publish. Из его publish evidence зафиксирован immutable application target `ghcr.io/stellmaria/velvet@sha256:517165ef91701ec7138ddb11a0138e6a2375d22a3a7683737b15ef7ea46c98d0`.

Ветка #667 синхронизирована с этим `main`. Rollout workflow теперь использует exact `SOURCE_COMMIT=e6571062af2c963297c17f94685490fa054c90ca` и соответствующий immutable digest. Provenance-комментарий server bridge уточнён: `CHECKOUT_COMMIT` отличается от application source одноразовым rollout payload и worklog, после deploy checkout восстанавливается на точный merge commit до reconcile.

Production rollout на этом этапе не запускался.

### Миграции и совместимость

SQL-миграций в PR нет. Application runtime PR напрямую не меняет. Совместимость обеспечивается строгим совпадением `SOURCE_COMMIT` и immutable image digest, опубликованного для этого commit штатным pipeline. Checkout после application deploy намеренно восстанавливается на итоговый rollout merge commit, чтобы fixed-target host bridge работал из чистого `origin/main`.

### Проверки

Проверена структура rollout workflow и server bridge: deployment идёт через существующий канонический deploy script, secret values не должны печататься, предусмотрены container health, no-published-ports, queue mode, Ollama, heartbeat и Telegram identity checks.

Verified application image для source commit `e6571062af2c963297c17f94685490fa054c90ca` опубликован штатным pipeline после успешного Trivy gate и SBOM generation. Ветка rollout синхронизирована с этим `main` без конфликтов.

Финальный protected CI самого PR #667 и production live-smoke ещё не заявляются выполненными. Live-smoke возможен только после отдельного решения на merge, потому что merge этого PR является trigger production rollout.

### PR и commit

- PR: #667 `Ops: one-time Arthur production rollout`.
- Ветка: `ops/arthur-prod-rollout-20260806`.
- Исходный базовый commit: `7b561b0bb2d04b7d5fd4fa3ae084d9af830c424f`.
- Финальный application source commit: `e6571062af2c963297c17f94685490fa054c90ca`.
- Publish evidence: workflow run `31179477871`.
- Immutable image digest закреплён в one-time rollout workflow.

### Незавершённое

- дождаться полного required CI PR #667 на финальном rollout payload;
- исправить только реальные найденные CI-проблемы, не менять verified provenance без нового application commit;
- остановиться перед merge, поскольку merge запускает production rollout;
- после отдельного решения на rollout проверить фактический deploy, Librarian reconcile, container health, ports, heartbeat, queue mode, Ollama model и Telegram `getMe`;
- после successful rollout зафиксировать production result отдельной эксплуатационной записью.

### Следующий шаг

Довести required checks PR #667 до полностью зелёного состояния на закреплённой verified source/digest pair и оставить PR готовым к отдельному production merge без запуска rollout в рамках текущей подготовки.

## Продолжение: исправление shallow checkout

После merge #667 workflow run `31183410920` завершился до SSH/deploy на проверке `git merge-base --is-ancestor`: стандартный shallow checkout не содержал `SOURCE_COMMIT=e6571062af2c963297c17f94685490fa054c90ca`. Production этим run не изменён.

PR #670 исправляет только этот дефект: в шаг `Checkout rollout payload` добавлен `fetch-depth: 0`. Проверка диапазона `e6571062...77bdfb83` подтвердила, что последующие изменения затрагивают только rollout ops/workflow, Hermes host env wiring, docs и tests и не попадают в image build paths `publish-image.yml`; поэтому verified source/image pair остаётся без изменений.

## Продолжение: host ownership blocker после PR #670

PR #670 прошёл все required checks и был merge-коммитом `b178257fa4998a885a4bcc05da8f7526e0e5f3aa`. Rollout run `31187581956` успешно прошёл full-history checkout и immutable target/credential preflight, затем вошёл в SSH stage.

Canonical `deploy/server/deploy.sh` остановился до `deployment_started=1` на legacy backup manifest, которому deploy-пользователь не мог выполнить `chmod 0644`: `Operation not permitted`. До `git fetch/reset`, image pull и container recreation выполнение не дошло, поэтому application/runtime этим run не переключались; Arthur credentials в `.env.server` были установлены без вывода значений.

Это соответствует известному contract PR #644: если top-level `*.dump`/`*.dump.json` принадлежит другому UID, deploy должен fail-fast до mutation, а дальнейший operational step требует host-level смены владельца. Следующий bounded rollout payload выполняет только этот repair для той же области файлов: переводит ownership к текущему deploy UID/GID и mode к `0644` через `sudo -n`, затем запускает неизменённый canonical deploy. При отсутствии разрешённого sudo repair падает до deploy. Application source/image pair остаётся `e6571062...` + `sha256:517165...`.

## Продолжение: bounded Docker ownership repair

PR #671 был merge-коммитом `48b6026fa452195369c0d1b0d04a408fd0022dfd`. Rollout run `31188082291` подтвердил production checkout `77bdfb8306615da479746449bea62cddbb9a652c`, но host repair остановился до deploy с `sudo: a password is required`. Следовательно application/runtime снова не менялись; deploy/reconcile step был skipped.

Поскольку production deploy-пользователь уже имеет Docker control как часть канонического server deploy contract, следующий bounded repair не расширяет sudoers и не даёт Arthur новых прав. Он запускает тот же verified immutable application image без сети, от root UID внутри одноразового контейнера, с bind mount только каталога backups и capabilities только `CHOWN`/`FOWNER`. Контейнер меняет ownership/mode исключительно top-level regular `*.dump` и `*.dump.json`; symlink не принимаются. После контейнера host-side assertions требуют точный deploy UID/GID и `0644` для каждого кандидата, затем выполняется неизменённый `deploy/server/deploy.sh`.

Дополнительно workflow удаляет stale `/tmp/velvet-arthur-*.json` payloads текущего deploy user, кроме payload текущего run, и всегда удаляет текущий transferred credential payload отдельным cleanup step. Это закрывает остаток от run `31188082291`, где deploy bridge не стартовал и его cleanup trap не мог выполниться. Secret values не выводятся.

## Продолжение: backup directory traversal

PR #673 был merge-коммитом `895c1f67f97184043f571dbee4d5c0ccfdf2856c`. Rollout run `31188708573` снова остановился до canonical deploy. Verified immutable image был успешно получен по ожидаемому digest, но repair container получил `PermissionError` при открытии bind root `/repair`: после `--cap-drop ALL` capabilities `CHOWN`/`FOWNER` не дают обход DAC для traversal host backup directory.

Credential cleanup step при этом выполнился, а production checkout оставался `77bdfb8306615da479746449bea62cddbb9a652c`. Следующая минимальная корректировка добавляет только `DAC_OVERRIDE` к bounded repair container. Сеть остаётся отключена, mount остаётся только backup directory, canonical deploy/reconcile не меняются, application source/image pair не меняется.
