# Сессия: verified production Librarian reconcile

- Дата: 2026-08-08
- ID: `2026-08-08-production-librarian-reconcile`
- Линия/фаза: Storage Librarian / production rollout follow-up
- Статус: частично
- Ветка: `ops/production-librarian-reconcile`
- Базовый commit: `328749227e26a8bfc8fc39447bf9782b9b040f2a`
- PR: #707

## Перед началом

### Цель

Закрыть разрыв между успешным server deploy нового Storage Librarian context-budget fix и отдельным Arthur Librarian runtime: добавить постоянный manual production entrypoint, который принимает exact deployed application source SHA и immutable verified Velvet image digest, безопасно синхронизирует production checkout с current `main` только через доказанный control-plane-only diff, закрепляет digest для Arthur и выполняет fixed-target reconcile `librarian`.

### Исходный контекст

PR #703 уже merged в `main` как `328749227e26a8bfc8fc39447bf9782b9b040f2a`. Production deploy run `31221717573` завершился `success` и подтвердил:

- production checkout обновлён до exact `328749227e26a8bfc8fc39447bf9782b9b040f2a`;
- core bot запущен на immutable image `ghcr.io/stellmaria/velvet@sha256:c97b445387bfc4c6e579a83408d67cdfefcb5e2cf7695710971bba6c1ee108f3`;
- image revision совпадает с deployed SHA;
- pre-deploy PostgreSQL dump проверен;
- server smoke прошёл, core bot/postgres/supervisor healthy.

Повторная read-only production diagnostics после deploy показала clean `main` checkout и active `velvet-librarian.service`, но `arthur` и `arthur-storage-gateway` всё ещё работали на предыдущем digest `sha256:517165ef...`. Поэтому проверка нового text budget в Arthur до reconcile была бы проверкой старого image.

Существующий `.github/workflows/arthur-production-reconcile-continuation.yml` не подходит для повторного использования, потому что содержит прежние hard-coded source/image значения. `.github/workflows/hermes-reconcile.yml` является CI validator и не выполняет production mutation.

Сам merge нового reconcile workflow создаёт control-plane commit поверх уже развернутого application source. Поэтому workflow разделяет две идентичности: `source_commit` обозначает immutable application source из image provenance, а `CHECKOUT_COMMIT=${{ github.sha }}` обозначает current `main`, содержащий control-plane workflow. Это позволяет не пересобирать и не деплоить идентичное приложение только ради workflow/docs/tests commit.

### Планируемый объём

- добавить manual-only `.github/workflows/reconcile-production-librarian.yml`;
- разрешать job только на `main` и только при confirmation `RECONCILE_LIBRARIAN`;
- требовать exact 40-character deployed application `source_commit`;
- требовать immutable `ghcr.io/stellmaria/velvet@sha256:<64 hex>`;
- проверять, что requested source является ancestor current workflow checkout;
- принимать production checkout только если он уже равен deployed source или current `main`, worktree clean;
- разрешать drift `source_commit..CHECKOUT_COMMIT` только в `.github/**`, `docs/**`, `tests/**`; любой runtime/deploy path fail-closed требует normal verified production deploy;
- до изменения env доказать, что core bot healthy, реально использует requested image digest/image ID, а OCI revision равен deployed application source;
- после safe control-plane gate синхронизировать clean production checkout на current `main` фиксированным `git reset --hard CHECKOUT_COMMIT` без force push;
- проверить `STORAGE_LIBRARIAN_AUTO_ENQUEUE=false`;
- атомарно обновить только persisted `VELVET_IMAGE` в `.env.server`, не печатая secrets;
- выполнить только `reconcilectl.py submit librarian` и дождаться terminal `completed`;
- восстановить owner/group `.git/index` узким verified-image repair при root ownership drift;
- проверить `ollama-librarian`, `librarian-hermes`, `arthur-storage-gateway`, `arthur` как healthy;
- проверить exact image для Arthur/gateway, отсутствие published host ports и heartbeat;
- проверить `StorageLibrarianSettings.from_env().max_text_chars == 11520` при standard text context `8192/384`, включая backward-compatible clamp legacy high env value;
- подтвердить `STORAGE_LIBRARIAN_AUTO_ENQUEUE=false` после reconcile;
- не запускать mass enqueue, vision acceptance или arbitrary reconcile target.

### Критерии готовности

- protected CI PR полностью зелёный на exact head;
- final diff ограничен workflow, contract test и этой worklog записью;
- current `main` перед merge не ушёл вперёд либо ветка безопасно синхронизирована без force;
- workflow не содержит push trigger, arbitrary reconcile target, `submit all`, mass enqueue или force push;
- current workflow checkout содержит deployed application source в ancestry;
- production checkout drift от image source до current main содержит только `.github/docs/tests` paths; иначе operation отказывается без mutation;
- core bot до reconcile доказывает requested immutable image reference, image ID и application revision;
- reconcile завершается `completed`;
- Arthur/gateway используют exact verified image;
- four-service Librarian stack healthy без published host ports;
- Arthur heartbeat присутствует;
- effective text source limit равен `11520`;
- automatic enqueue остаётся выключен;
- final production checkout равен current main, clean, `.git/index` доступен deploy user.

### Риски и ограничения

Workflow намеренно обновляет persisted `VELVET_IMAGE` только после доказательства, что уже работающий core bot использует тот же immutable image и его OCI revision совпадает с requested application source commit. Это предотвращает подмену Arthur произвольным digest.

Control-plane bootstrap разрешён только для `.github/**`, `docs/**`, `tests/**`. Если после image source в `main` появился любой application, deploy, script или другой path, workflow завершится до checkout/env mutation и потребует обычный verified production deploy. Тем самым manual reconcile не превращается в скрытый механизм деплоя runtime-кода.

После начала reconcile workflow не откатывает `VELVET_IMAGE` на старый digest при runtime failure: старый pin уже является причиной version skew, а автоматический rollback pin мог бы создать ещё более неоднозначное частично обновлённое состояние. Failed reconcile остаётся fail-closed с новым verified desired image и требует повторной диагностики/retry.

Vision/VLM acceptance остаётся отдельным #630. `STORAGE_LIBRARIAN_AUTO_ENQUEUE=false` сохраняется, mass/backfill enqueue не выполняется. SQL migrations отсутствуют.

## После завершения

### Фактически сделано

Добавлены постоянный manual production workflow и отдельный contract test. Workflow использует production environment secrets только для bounded SSH до canonical checkout, отделяет immutable application provenance от current control-plane checkout, сохраняет manual-only queue mode и вызывает только fixed target `librarian` через уже установленный reconcile control plane.

До production mutation workflow подтверждает healthy core bot на requested immutable image и OCI revision application source. Затем он допускает checkout fast-forward только при control-plane-only `.github/docs/tests` diff; иначе требует normal production deploy.

Post-reconcile gate проверяет exact Arthur/gateway image ID и reference, health всех четырёх Librarian services, отсутствие published ports, heartbeat, text Ollama model и effective Storage Librarian text source limit `11520`.

### Миграции и совместимость

Application/SQL migrations отсутствуют. Изменение добавляет control-plane entrypoint и не меняет runtime application code. Legacy explicit `STORAGE_LIBRARIAN_MAX_TEXT_CHARS=120000` остаётся совместимым: новый application code clamp-ит effective value до `11520` при standard `8192/384`.

### Проверки

Первый CI head `b0c5e1763cf61bdb57cdf280fb89fa0dca37ee4c` подтвердил branch-protection contract, но `project notes contract` корректно потребовал отдельную worklog запись.

Второй head `94156acde36ae23df124d636ad22ea441fc81ffa` подтвердил `type check`, а project-notes gate уточнил допустимый terminal status worklog: `заблокировано`, `завершено` или `частично`. Статус изменён на `частично`, одновременно устранён bootstrap-парадокс source SHA/current main через отдельный control-plane checkout contract. После этих изменений все required checks должны быть повторно проверены на новом exact head.

### PR и commit

- Ветка: `ops/production-librarian-reconcile`.
- PR: #707.
- База на старте: `328749227e26a8bfc8fc39447bf9782b9b040f2a`.

### Незавершённое

- дождаться полностью зелёного protected CI на новом exact head;
- перед merge повторно проверить current `main`, behind/overlap и final changed-file scope;
- merge #707 только на exact green head;
- после merge запустить новый manual `reconcile production Librarian` с application source `328749227e26a8bfc8fc39447bf9782b9b040f2a` и verified image `ghcr.io/stellmaria/velvet@sha256:c97b445387bfc4c6e579a83408d67cdfefcb5e2cf7695710971bba6c1ee108f3`;
- затем выполнить production runtime acceptance и ручные Telegram проверки `/status`, небольшой `/analyze`, `/result` и oversized fail-closed.

### Следующий шаг

Получить terminal green CI для #707, безопасно merge в `main`, затем использовать новый workflow для verified production Librarian reconcile без повторного application deploy и без mass enqueue.
