# Arthur archive control / VL priority integration

- Дата: 2026-08-08
- ID: `arthur-archive-vl-gate-integration-20260808`
- Линия/фаза: VL / Arthur Storage Librarian scheduling integration
- Статус: `частично`
- Ветка: `fix/arthur-archive-vl-gate-main-20260808`
- Базовый commit: `66f0993780a1428b260336929f2050b424aebf1e`
- Канонический VL источник: issue #630

## Перед началом

### Исходный контекст

PR #741 ввёл repository-backed gate `Arthur full-archive → automatic Qwen/VL`, но его activation predicate был привязан к legacy env mode `STORAGE_LIBRARIAN_AUTO_ENQUEUE=true` + `STORAGE_LIBRARIAN_AUTO_BACKFILL=true`.

PR #742 заменил production archive control на owner-only `/archive start|stop|status` внутри отдельного Arthur container/process и намеренно сохранил deployment contract `STORAGE_LIBRARIAN_AUTO_ENQUEUE=false`. После совместного merge это создало semantic gap: Telegram-managed full-archive мог быть активен, а #741 gate в основном bot process считал full-archive выключенным и разрешал automatic VL claim.

Production verified deploy `a392df96e1cd113ff5bbe6e6e22246984d6b50ec` не включает automatic Qwen queue, поэтому конфликт обнаружен до activation.

### Цель

Состыковать #741 и #742 без возврата к env-driven background scheduler: `/archive start` должен публиковать межконтейнерный phase lease, а automatic VL должен по-прежнему открываться только после доказанного исчерпания текущего Storage archive backlog.

### Планируемый объём

- использовать PostgreSQL session advisory lock как cross-process Arthur archive lease без новой таблицы и миграции;
- держать lease на одной выделенной DB connection весь lifetime `/archive start` task;
- получать lease синхронно внутри `start_archive()` до успешного ответа владельцу и до запуска archive loop, чтобы убрать окно для VL claim;
- полагаться на автоматическое освобождение PostgreSQL advisory lock при crash/disconnect Arthur process;
- main bot должен проверять тот же lease до automatic VL claim;
- при active lease повторно использовать существующие repository counts и `enqueue_pending(limit=1)` probe;
- не блокировать VL навсегда только потому, что `/archive start` task остаётся жив и ждёт новые объекты;
- сохранить legacy env full-archive activation как совместимый путь;
- не включать production VL flags и не менять model routing этим PR.

### Критерии готовности

- env scheduler остаётся выключенным (`AUTO_ENQUEUE=false`, `AUTO_BACKFILL=false`), но active Arthur advisory lease всё равно включает VL priority gate;
- успешный `start_archive()` возвращается только после фактического acquire cross-container lease;
- недоступный lease не создаёт ложный active archive task;
- lease probe не оставляет advisory lock в main bot connection pool, когда Arthur archive не активен;
- чужой active lease распознаётся без попытки его unlock;
- Arthur archive task держит lease до фактического выхода, включая cooperative stop текущего object inference;
- queued/running Storage job блокирует VL до `claim_next`;
- residual eligible Storage backlog ставит максимум один bounded probe job и держит VL закрытым;
- пустые counts плюс `enqueue_pending(..., limit=1) == 0` открывают VL даже при живом `/archive start` loop;
- ошибки lease probe блокируют automatic VL fail-closed;
- legacy env full-archive gate сохраняет прежнее поведение;
- protected CI зелёный на exact PR head и branch не отстаёт от `main` перед merge.

### Риски и ограничения

- Arthur удерживает одну connection из собственного asyncpg pool на время archive phase; pool настроен до 10 connections;
- advisory lock является межпроцессным через общий PostgreSQL, но не переживает потерю DB session, что здесь намеренно: crash/disconnect автоматически снимает stale lease;
- уже начатый единичный VL inference не отменяется, если новый Storage object появляется после открытия gate;
- explicit manual Arthur `/analyze` не становится отдельным global preemption primitive этим изменением;
- `/archive stop` может оставить ранее queued Storage rows для последующего resume; после фактического stop они не удерживают archive priority сами по себе;
- mass VL backfill остаётся запрещён до acceptance и owner approval по issue #630.

## После завершения

### Фактически сделано

`ArthurStorageLibrarianRepository` получил единый PostgreSQL advisory-lock key и два bounded coordination API:

- `full_archive_phase()` удерживает session advisory lock на выделенной DB connection и освобождает его в `finally`;
- `full_archive_phase_active()` пробует тот же lock из main bot, немедленно освобождает временно полученный lock при inactive Arthur и возвращает active, если lock уже удерживает другой process.

`ArthurLibrarianApplication.start_archive()` теперь сначала входит в `full_archive_phase()` и только после успешного acquire создаёт archive task и возвращает `True`. Поэтому нет окна между успешным `/archive start` и публикацией cross-container lease. Если lease занят или acquire не удался, task не создаётся. Archive task получает уже удерживаемый context и освобождает его только в своём `finally`, после текущего object boundary и cooperative stop.

`storage_librarian_full_archive_has_priority()` активируется двумя совместимыми путями:

1. explicit Arthur `/archive start` PostgreSQL lease;
2. legacy env full-archive mode для обратной совместимости.

После activation gate сохраняет repository-backed semantics #741: сначала `queued/running`, затем bounded `enqueue_pending(limit=1)` probe. Поэтому живой Arthur archive loop без остаточного backlog не блокирует Qwen навсегда.

### Миграции и совместимость

SQL migrations отсутствуют. Advisory lock не создаёт persisted rows и не меняет схему Storage Librarian jobs/analysis. Если Arthur process или его PostgreSQL session завершается, сервер БД освобождает session advisory lock автоматически, поэтому отдельный stale-state recovery для archive lease не нужен.

Legacy env-driven full-archive activation остаётся совместимым: при `STORAGE_LIBRARIAN_AUTO_ENQUEUE=true` + `STORAGE_LIBRARIAN_AUTO_BACKFILL=true` gate сохраняет прежний repository-backed путь. Production contract #742 с env `false/false` получает cross-container activation через Arthur advisory lease. Новых обязательных env vars нет.

### Проверки

Regression coverage расширен так, чтобы проверять:

- inactive advisory probe берёт и сразу освобождает временный lock;
- active foreign lease определяется без `pg_advisory_unlock` чужой сессии;
- archive phase context берёт и освобождает ровно один session lock;
- успешный archive start уже держит lease в момент возврата;
- failure acquire не оставляет `_archive_task`;
- active Arthur lease при env scheduler `false/false` блокирует VL;
- residual backlog и empty-backlog semantics сохраняют bounded #741 probe;
- lease probe failure блокирует VL fail-closed;
- cooperative archive stop удерживает lease до фактического выхода task;
- существующий consumer-before-claim contract остаётся покрыт.

Generated package architecture и repository layout inventory пересчитаны штатными repo scripts на Python `3.13`, то есть той же major/minor версией, которую использует CI preflight. До push отдельно прошли full package `--check`, fast package `--check` и repository-layout `--check`. Package inventory фиксирует `production_loc=146496`; новых production modules или repository modules интеграция не добавляет. Проверенный generated refresh завершился commit `4424baeb35b383b5cc153605499e74a16d49a1b8`.

### PR и commit

- Preflight PR `#745` использовался только для поиска contract/inventory findings и закрыт без merge после переноса final tree на актуальный `main`.
- Финальный merge-кандидат: PR `#746` — `Integrate Arthur archive control with automatic VL priority`.
- Финальная ветка: `fix/arthur-archive-vl-gate-main-20260808`.
- Базовый commit финальной ветки: `66f0993780a1428b260336929f2050b424aebf1e`.
- Перед открытием PR #746 compare к `main` показал `behind_by=0` и merge base exact `66f0993780a1428b260336929f2050b424aebf1e`.
- Финальный exact head и squash merge commit фиксируются после terminal success required CI.

### Незавершённое

- protected CI ещё не завершён на final exact head PR #746;
- PR #746 ещё не merged;
- production verified image с этой интеграцией ещё не опубликован и не развёрнут;
- canonical LOCAL_MAIN single-image `512 / 1` acceptance ещё не выполнен;
- automatic Qwen queue остаётся выключенной до acceptance.

### Следующий шаг

Дождаться terminal success required checks на exact PR #746 head, повторно проверить актуальный `main` и `behind_by=0`, выполнить authorized squash merge и развернуть новый verified immutable application image в main bot и Arthur profile. После production verification перейти к canonical `512 / 1` acceptance, не включая automatic Qwen queue заранее.
