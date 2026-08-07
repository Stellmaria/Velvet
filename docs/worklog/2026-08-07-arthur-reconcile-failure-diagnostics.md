# Сессия: diagnostics повторного Arthur reconcile failure

- Дата: 2026-08-07
- ID: `2026-08-07-arthur-reconcile-failure-diagnostics`
- Линия/фаза: Arthur Librarian Phase 2 / production acceptance (#586)
- Статус: частично
- Ветка: `ops/arthur-reconcile-failure-diagnostics`
- Базовый commit: `5ea7a7cfaa055481ce513db3bbb42400e3442649`
- PR: pending

## Перед началом

### Цель

Снять свежий read-only production evidence после fixed-target reconcile task `reconcile_20e0b7deb8924f1ab065eb88d4fa313d`, который повторно упал при запуске `velvet-librarian.service` уже после успешного persisted immutable image pin.

### Исходный контекст

Reconcile-only continuation run `31195796153` не выполнял повторный server deploy. Он успешно синхронизировал production checkout на exact merge SHA `5ea7a7cfaa055481ce513db3bbb42400e3442649`, подтвердил persisted `VELVET_IMAGE` exact verified digest, `STORAGE_LIBRARIAN_AUTO_ENQUEUE=false` и healthy main bot на immutable image из successful deploy run `31195032933`.

Fixed target `librarian` был принят как task `reconcile_20e0b7deb8924f1ab065eb88d4fa313d`, но после Brain Vault/context/credentials/local-only checks снова завершился `failed` на `velvet-librarian.service`. EXIT cleanup успешно восстановил production `.git/index` owner/group deploy user, поэтому previous root-index debt не оставлен после failure.

Stale `velvet-bot:local` уже не может считаться достаточным объяснением: persisted immutable image pin был проверен перед submit. Нужен свежий journal/container evidence именно после task `reconcile_20e0b7deb8924f1ab065eb88d4fa313d`.

### Планируемый объём

- добавить одноразовый read-only diagnostics workflow;
- использовать только deploy SSH credentials, без Arthur bot/gateway secrets;
- не выполнять deploy, reconcile, restart, pull или filesystem mutation;
- зафиксировать checkout/index state и boolean image-pin/manual-only checks без вывода env;
- снять bounded `systemctl show/status` и recent journal `velvet-librarian.service` с redaction;
- снять Compose/container state и exact `.Config.Image` для Arthur services;
- снять bounded gateway/Arthur container logs с redaction;
- проверить Ollama model inventory и disk/RAM/swap;
- использовать evidence как единственный источник следующего remediation slice.

### Критерии готовности

- protected CI diagnostics PR зелёный;
- production probe не выполняет runtime mutation;
- exact unit failure и/или failing Arthur container stage установлены;
- подтверждено, использует ли gateway exact immutable image после pin;
- `.git/index` остаётся deploy-owned и checkout clean;
- secrets/tokens/database credentials не публикуются.

### Риски и ограничения

Systemd и container logs могут содержать application strings, поэтому workflow пропускает output через redactor для bearer/token/api-key/password, Telegram token shape, PostgreSQL credentials и GitHub tokens. `.env.server` читается только parser’ом для сравнения двух несекретных contract values и не печатается.

Vision/VLM implementation не входит в scope и остаётся #630. Diagnostics не включает mass enqueue или cloud/provider calls.

## После завершения

### Фактически сделано

Добавлен `.github/workflows/arthur-production-reconcile-failure-diagnostics.yml` в общей `velvet-production` concurrency group. Workflow read-only снимает checkout/index state, image pin/manual-only status, systemd status/journal, Compose state, container identity, bounded gateway/Arthur logs, Ollama models и host resources.

### Миграции и совместимость

SQL/application migrations отсутствуют. Production application image/source не меняются. Workflow не вызывает canonical deploy или fixed-target reconcile.

### Проверки

Production probe ещё не запущен. До merge требуется полный protected CI и current-main check.

### PR и commit

- Ветка: `ops/arthur-reconcile-failure-diagnostics`.
- База: `5ea7a7cfaa055481ce513db3bbb42400e3442649`.
- Workflow commit: `45f5f14b942036152d6ec5ab18b05dfaedf016e8`.

### Незавершённое

- открыть diagnostics PR и пройти protected CI;
- выполнить read-only production probe;
- определить exact service/container blocker;
- реализовать только подтверждённый bounded fix;
- повторить fixed-target reconcile и automated Arthur gates;
- после automated success выполнить manual live acceptance #586.

### Следующий шаг

Слить diagnostics-only PR после зелёного CI и использовать его redacted production evidence для следующего remediation без speculative restart/deploy.
