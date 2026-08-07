# Сессия: Arthur rollout с repair Git index и activation reconcile bridge

- Дата: 2026-08-07
- ID: `2026-08-07-arthur-production-rollout-index-reconcile`
- Линия/фаза: Arthur Librarian Phase 2 / production acceptance (#586)
- Статус: частично
- Ветка: `ops/arthur-rollout-repair-index-activate-reconcile`
- Базовый commit: `741cd9c76beda241be5c9e626f0dfbaf9c66416b`
- PR: pending

## Перед началом

### Цель

Выполнить следующий bounded production rollout после двух подтверждённых blockers: восстановить ownership единственного повреждённого production `.git/index`, развернуть прежнюю verified application source/image pair canonical deploy-путём, активировать исправленный Hermes reconcile bridge и получить completed fixed-target Librarian reconcile с полным Arthur automated acceptance.

### Исходный контекст

Rollout run `31192847516` остановился до deployment mutation на `fatal: .git/index: index file open failed: Permission denied`. Read-only diagnostics run `31193612593` подтвердил exact state: production checkout и `.git` принадлежат deploy user `1000:1000`, все остальные top-level Git metadata принадлежат этому же user, а только `.git/index` имеет `root:root 0640`. Поэтому broad checkout ownership repair не нужен и недопустим.

PR #684 (`741cd9c76beda241be5c9e626f0dfbaf9c66416b`) исправил durable root cause: production Hermes reconcile entrypoint теперь вызывает Git с `--no-optional-locks` и exact `safe.directory`, а regression test фиксирует этот contract. Specialized `hermes reconcile` CI и весь protected CI прошли.

Read-only diagnostics run `31194301458` после merge #684 подтвердил `reconcile_installer_sudo=allowed` для exact canonical `/usr/bin/bash <APP_DIR>/deploy/hermes-reconcile/install.sh`. Текущий production checkout при этом остаётся `558f846040fed92ac3935f2fce2dcbd52a284946`, `.git/index` всё ещё `root:root 0640`, а старый Librarian unit остаётся failed со stale `velvet-bot:local` gateway из предыдущего reconcile.

Verified application provenance не меняется:

- source: `e6571062af2c963297c17f94685490fa054c90ca`;
- image: `ghcr.io/stellmaria/velvet@sha256:517165ef91701ec7138ddb11a0138e6a2375d22a3a7683737b15ef7ea46c98d0`;
- publish evidence: run `31179477871`.

Изменения после source commit относятся к rollout/reconcile/docs/tests/host wiring и не входят в production image publish paths.

### Планируемый объём

- до любых Git status/fetch operations проверить ownership checkout root и `.git`;
- one-time repair выполнять только для `.git/index`, только если UID/GID отличаются от deploy user;
- не менять permission bits index: repair делает только `chown`, сохраняя текущий mode;
- repair выполнять тем же verified immutable Velvet image, `--network none`, root только внутри transient container, с единственной capability `CHOWN` и bind mount только `.git`;
- после repair требовать deploy ownership, read/write index и clean `GIT_OPTIONAL_LOCKS=0 git status`;
- сохранить существующий bounded legacy backup ownership repair;
- выполнить canonical `deploy/server/deploy.sh` с прежней verified source/image pair;
- только после deploy success закрепить `VELVET_IMAGE` в `.env.server` на exact immutable digest;
- восстановить checkout на exact rollout merge SHA с `umask 022`;
- безусловно активировать текущий canonical Hermes reconcile bridge через exact permitted `sudo -n /usr/bin/bash deploy/hermes-reconcile/install.sh`;
- выполнить fixed-target `reconcilectl submit librarian` и дождаться `completed`;
- после root reconcile доказать, что `.git/index` остался owned deploy user и clean Git status доступен;
- выполнить существующие Arthur health/image/ports/heartbeat/manual-only/Ollama/getMe gates;
- не включать mass/AFK enqueue, archive backfill или vision scope.

### Критерии готовности

- protected CI rollout PR полностью зелёный;
- current `main` перед merge не содержит новых application-image changes без нового publish evidence;
- one-time index repair затрагивает только `.git/index` и не меняет его mode;
- canonical deploy завершается успешно на source `e6571062...` / verified digest;
- `.env.server VELVET_IMAGE` закреплён только после deploy success;
- canonical Hermes reconcile installer успешно активирует entrypoint с durable optional-lock suppression;
- Librarian reconcile завершается `completed`;
- после reconcile `.git/index` остаётся owned deploy UID/GID, readable/writable и production checkout clean;
- `ollama-librarian`, `librarian-hermes`, `arthur-storage-gateway`, `arthur` healthy/running;
- Arthur/gateway используют exact verified immutable image;
- нет published host ports;
- `/tmp/arthur-heartbeat` существует;
- `STORAGE_LIBRARIAN_AUTO_ENQUEUE=false`;
- `ollama show velvet-librarian-text:v1` успешен;
- Telegram `getMe` успешен;
- final checkout равен exact rollout merge SHA и job содержит final `Arthur production rollout verified ...` marker.

### Риски и ограничения

Git metadata repair является production filesystem mutation, но ограничен единственным подтверждённым regular non-symlink `.git/index`; broad recursive chown запрещён. Permission bits намеренно не нормализуются вручную. Canonical deploy и post-deploy checkout reset выполняют собственные Git operations после восстановления owner access.

Activation reconcile installer является root operation, но используется только existing canonical script, exact sudo capability которого подтверждена read-only production probe. Никаких произвольных root shell commands в rollout не добавляется.

Vision/VLM остаётся scope #630. Наличие уже скачанного vision alias не является acceptance и не должно расширять #586. `STORAGE_LIBRARIAN_AUTO_ENQUEUE=false` остаётся обязательным.

## После завершения

### Фактически сделано

Workflow `.github/workflows/arthur-production-rollout-v2.yml` расширен pre-deploy repair внутри существующего ownership step. Он проверяет checkout/.git boundaries, при необходимости запускает transient verified-image container с `--network none`, `--cap-drop ALL`, `--cap-add CHOWN` и bind mount только `.git`, затем меняет owner/group только `/repair/index`. Mode index сохраняется.

Server bridge `.github/ops/arthur-production-rollout.sh` теперь использует `GIT_OPTIONAL_LOCKS=0` для clean-tree checks, выполняет post-deploy fetch/reset в subshell с `umask 022`, безусловно запускает exact canonical reconcile installer перед fixed-target submit и после `completed` проверяет ownership/read-write status `.git/index` как production regression gate.

Существующий immutable image pin и Arthur runtime exact-image assertions сохранены.

### Миграции и совместимость

SQL/application migrations отсутствуют. `SOURCE_COMMIT` и `IMAGE_DIGEST` не менялись. Rollout changes находятся в ops/workflow/worklog и не требуют нового application image.

### Проверки

До production merge требуется полный protected CI этого PR и повторная provenance-проверка current `main`. Production rollout в этой ветке ещё не выполнялся.

### PR и commit

- Ветка: `ops/arthur-rollout-repair-index-activate-reconcile`.
- База: `741cd9c76beda241be5c9e626f0dfbaf9c66416b`.
- Workflow change: `8cd00f62216dc6a63fd537a4a5366510de1e8f5c`.
- Bridge change: `7c23f8e6f7b778c10acde9d163accaa5105b0063`.

### Незавершённое

- открыть rollout PR и пройти protected CI;
- проверить current `main` и application provenance перед merge;
- выполнить production rollout и разобрать exact repair/deploy/reconcile/health evidence;
- после automated acceptance выполнить manual live Telegram/storage/answer workflow, PostgreSQL persisted result, zero-provider evidence, latency/resources и restart/reconcile persistence;
- только после полного acceptance обновить/закрыть #586.

### Следующий шаг

Открыть bounded rollout PR, получить полностью зелёный CI и merge только при сохранённой verified application provenance; затем принять production run исключительно при completed reconcile, healthy Arthur stack, сохранённом Git-index ownership и final verification marker.
