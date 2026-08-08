# Arthur archive control / VL priority integration

- Дата: 2026-08-08
- ID: `arthur-archive-vl-gate-integration-20260808`
- Линия/фаза: VL / Arthur Storage Librarian scheduling integration
- Статус: `частично`
- Ветка: `fix/arthur-archive-vl-gate-20260808`
- Базовый commit: `a392df96e1cd113ff5bbe6e6e22246984d6b50ec`
- Канонический VL источник: issue #630

## Перед началом

### Исходный контекст

PR #741 ввёл repository-backed gate `Arthur full-archive → automatic Qwen/VL`, но его activation predicate был привязан к legacy env mode `STORAGE_LIBRARIAN_AUTO_ENQUEUE=true` + `STORAGE_LIBRARIAN_AUTO_BACKFILL=true`.

PR #742 заменил production archive control на owner-only `/archive start|stop|status` внутри Arthur process и намеренно сохранил deployment contract `STORAGE_LIBRARIAN_AUTO_ENQUEUE=false`. После совместного merge это создало semantic gap: Telegram-managed full-archive мог быть активен, а #741 gate считал full-archive выключенным и разрешал automatic VL claim.

Production verified deploy `a392df96e1cd113ff5bbe6e6e22246984d6b50ec` не включает automatic Qwen queue, поэтому конфликт обнаружен до activation.

### Цель

Состыковать #741 и #742 без возврата к env-driven background scheduler: `/archive start` должен активировать Arthur phase signal, а automatic VL должен по-прежнему открываться только после доказанного исчерпания текущего Storage archive backlog.

### Планируемый объём

- добавить process-wide signal явной Arthur archive phase в существующий `local_ai_runtime` coordination module;
- выставлять signal при успешном `/archive start` и снимать только при фактическом завершении archive task;
- не снимать signal сразу по `/archive stop`, чтобы текущий Storage inference завершался без конкурирующего automatic VL;
- считать gate активным при runtime Arthur archive phase либо при legacy env full-archive mode;
- повторно использовать существующие repository counts и `enqueue_pending(limit=1)` probe;
- не блокировать VL навсегда только потому, что `/archive start` task остаётся жив и ждёт новые объекты;
- не включать production VL flags и не менять model routing этим PR.

### Критерии готовности

- env scheduler остаётся выключенным (`AUTO_ENQUEUE=false`, `AUTO_BACKFILL=false`), но active Arthur archive phase всё равно включает VL priority gate;
- queued/running Storage job блокирует VL до `claim_next`;
- residual eligible Storage backlog ставит максимум один bounded probe job и держит VL закрытым;
- пустые counts плюс `enqueue_pending(..., limit=1) == 0` открывают VL даже при живом `/archive start` loop;
- cooperative `/archive stop` удерживает phase signal до выхода archive task;
- после shutdown/stop completion signal очищается;
- legacy env full-archive gate сохраняет прежнее поведение;
- protected CI зелёный на exact PR head и branch не отстаёт от `main` перед merge.

### Риски и ограничения

- signal process-wide, а не межконтейнерный; он связывает Arthur archive controller и automatic VL consumer, работающие в одном application process;
- уже начатый единичный VL inference не отменяется, если новый Storage object появляется после открытия gate;
- explicit manual Arthur `/analyze` не становится отдельным global preemption primitive этим изменением;
- `/archive stop` может оставить ранее queued Storage rows для последующего resume; после фактического stop они не удерживают runtime archive priority сами по себе;
- mass VL backfill остаётся запрещён до acceptance и owner approval по issue #630.

## После завершения

### Фактически сделано

Добавлен process-wide Arthur archive phase signal в `velvet_bot/local_ai_runtime.py`. `ArthurLibrarianApplication.start_archive()` выставляет signal после создания archive task, а `_archive_loop()` очищает его только в `finally` при фактическом завершении task.

`storage_librarian_full_archive_has_priority()` теперь активируется двумя совместимыми путями:

1. explicit Arthur `/archive start` runtime phase;
2. legacy env full-archive mode для обратной совместимости.

После activation gate сохраняет repository-backed semantics #741: сначала `queued/running`, затем bounded `enqueue_pending(limit=1)` probe. Поэтому живой Arthur archive loop без остаточного backlog не блокирует Qwen навсегда.

### Проверки

Regression coverage расширен так, чтобы проверять:

- active Arthur archive phase при env scheduler `false/false` блокирует VL;
- start выставляет phase signal;
- cooperative stop не снимает signal преждевременно;
- shutdown/фактический выход archive task очищает signal;
- существующие #741 queue/probe и consumer-before-claim контракты остаются покрыты.

### Незавершённое

- generated architecture inventory должен быть синхронизирован, если protected preflight зафиксирует drift;
- protected CI ещё не завершён на final exact head;
- PR ещё не merged;
- production verified image с этой интеграцией ещё не опубликован и не развёрнут;
- canonical LOCAL_MAIN single-image `512 / 1` acceptance ещё не выполнен;
- automatic Qwen queue остаётся выключенной до acceptance.

### Следующий шаг

Открыть PR, устранить только фактические CI findings, дождаться terminal success required checks на exact head, проверить `behind_by=0`, выполнить authorized squash merge и развернуть новый verified immutable application image. После production verification перейти к canonical `512 / 1` acceptance, не включая automatic Qwen queue заранее.
