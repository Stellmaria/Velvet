# Сессия: Arthur production rollout run 6 и stdin boundary

- Дата: 2026-08-07
- ID: `2026-08-07-arthur-production-rollout-run6`
- Линия/фаза: Arthur Librarian Phase 2 / production acceptance (#586)
- Статус: частично
- Ветка: `ops/arthur-rollout-isolate-deploy-stdin`
- Базовый commit: `3696e266bae37b5df13bc90317fc5237d6d41ea5`
- PR: #679

## Перед началом

### Цель

Зафиксировать фактический результат production rollout run `31190120224`, не засчитать ложноположительный workflow success как Arthur acceptance и устранить границу stdin между streamed rollout bridge и canonical deploy.

### Исходный контекст

Run `31190120224` впервые успешно прошёл bounded backup ownership repair и реально запустил canonical `deploy/server/deploy.sh`. Verified application source остаётся `e6571062af2c963297c17f94685490fa054c90ca`, verified immutable image остаётся `ghcr.io/stellmaria/velvet@sha256:517165ef91701ec7138ddb11a0138e6a2375d22a3a7683737b15ef7ea46c98d0`.

Canonical deploy завершился успешно, однако Actions job не содержит `reconcilectl` submit/wait output и финального `Arthur production rollout verified ...` marker. Поэтому run 6 изменил production application runtime, но не доказывает выполнение post-deploy Arthur reconcile/health acceptance.

### Планируемый объём

- сохранить verified application source/image pair без изменений;
- отделить transport rollout bridge от его remote execution;
- передавать exact checked-out bridge во временный private host file;
- выполнять bridge как файл с stdin `/dev/null`;
- сохранить canonical `deploy/server/deploy.sh` и существующий fixed-target Librarian reconcile;
- удалять remote bridge и credential payload независимо от результата;
- повторить rollout и требовать явный final Arthur verification marker.

### Критерии готовности

- protected CI PR #679 полностью зелёный;
- следующий production run выполняет canonical deploy и продолжает execution после него;
- checkout восстанавливается на exact rollout merge SHA;
- `reconcilectl submit librarian` принят и wait завершается `completed`;
- Arthur runtime checks проходят до финального verification marker;
- secrets не выводятся и временные payload files удаляются.

### Риски и ограничения

Run 6 уже изменил production, поэтому дальнейшие запуски должны проверять rollback/final health и exact checkout SHA. Нельзя считать успешный основной Velvet deploy эквивалентом Arthur acceptance. Mass enqueue, `STORAGE_LIBRARIAN_AUTO_ENQUEUE=true`, vision/VLM scope, cloud/provider execution и альтернативный deployment path не допускаются.

## После завершения

### Фактически сделано

Run 6 прошёл full-history checkout, immutable target/credential preflight и bounded legacy backup ownership repair. Repair сообщил `files=38`.

Canonical `deploy/server/deploy.sh` создал и проверил pre-deploy PostgreSQL dump (`migrations=92`, `tables=105`, `characters=96`), reset-нул application checkout на verified source commit, pulled exact immutable image, запустил core services и bot, прошёл server smoke и явно сообщил `Velvet deployment succeeded: e6571062af2c963297c17f94685490fa054c90ca`.

Production application runtime этим run был изменён. Однако сразу после canonical deploy output Actions перешёл к cleanup step. В job log отсутствуют `reconcilectl` output и final Arthur verification marker.

PR #679 меняет workflow execution boundary: exact bridge сначала записывается во временный private file на host, затем выполняется этим же deploy user как file с stdin перенаправленным из `/dev/null`. Credential payload и remote bridge удаляются unconditional cleanup step.

### Миграции и совместимость

SQL-миграций и application runtime changes в PR #679 нет. Verified application source/image pair не меняется. Canonical server deploy и fixed-target Librarian reconcile logic внутри `.github/ops/arthur-production-rollout.sh` не изменяются.

### Проверки

Run 6 подтвердил healthy canonical Velvet deployment и server smoke для verified image. Отдельно проверено отсутствие в его job log строк `librarian reconcile` и `Arthur production rollout verified`, поэтому этот run намеренно не считается Arthur acceptance.

Новый workflow сохраняет SSH BatchMode/IdentitiesOnly boundaries, private temporary filenames и cleanup обоих transferred artifacts. Полный protected CI и повторный production rollout ещё должны завершиться.

### PR и commit

- PR: #679 `Ops: isolate Arthur rollout bridge stdin`.
- Базовый rollout merge SHA: `3696e266bae37b5df13bc90317fc5237d6d41ea5`.
- Run 6: `31190120224`.
- Verified application source: `e6571062af2c963297c17f94685490fa054c90ca`.
- Verified image digest: `sha256:517165ef91701ec7138ddb11a0138e6a2375d22a3a7683737b15ef7ea46c98d0`.

### Незавершённое

- получить полностью зелёный protected CI #679;
- проверить current `main` перед merge и не смешать provenance при новом application commit;
- merge #679 и разобрать повторный production rollout;
- подтвердить exact final checkout, completed Librarian reconcile и Arthur automated health gates;
- после этого выполнить live/manual acceptance #586: Telegram commands, persisted result, zero-provider evidence, latency/resources и restart persistence.

### Следующий шаг

Довести PR #679 до зелёного CI, затем повторить production rollout той же verified application pair и принять run только при наличии явного completed reconcile и финального `Arthur production rollout verified ...` marker.
