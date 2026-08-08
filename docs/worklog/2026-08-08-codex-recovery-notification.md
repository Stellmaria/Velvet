# Codex subscription recovery notification

- Дата: 2026-08-08
- ID: codex-recovery-notification
- Линия/фаза: Hermes Codex availability production UX
- Статус: `завершено в repo`
- Ветка: `feat/codex-recovery-notification`
- Базовый commit: `8b160db820592c36f51da491b0525754f6954bdf`

## Перед началом

### Цель

Добавить одно persistent-deduplicated Telegram-уведомление от основного Velvet-бота, когда ранее доказанный Codex subscription limit снимается и persisted dynamic gate после нового успешного live probe снова разрешает primary Codex routing.

### Исходный контекст

Dynamic Codex availability gate уже является единственным routing authority для Velvet coder, Max coder и GPT Image 2. Coder runtime выполняет startup probe, обязательный пятичасовой watcher и дополнительный reset-time probe, а `GET /v1/capabilities` публикует безопасный persisted `routing.codex_availability` без дополнительного quota request.

Main bot уже получает `CODEX_LIMITS_BASE_URL` и `CODEX_LIMITS_API_KEY`, а `bootstrap.py` создаёт один основной `ProtectedMediaBot` и передаёт его в централизованный `WorkerManager`. Поэтому recovery notification должна использовать этот bot/application path и не создавать отдельный Telegram token, process или quota watcher.

### Планируемый объём

- Наблюдать только `GET /v1/coders/{project}/capabilities`, не `/rate-limits`.
- Считать subscription limit доказанным только по persisted provider state `provider_available=false` и subscription reason.
- Считать recovery доказанным только когда оба project state доступны, `provider_available=true`, `codex_available=true`, `reason/provider_reason=available`, latest probe не содержит error и его `last_checked_at` новее ограничивающего snapshot.
- Хранить pool-level active event и dedupe marker в host-persisted `/app/runtime` main bot runtime.
- Отправлять одно сообщение через уже созданный основной bot в primary owner chat.
- Не менять пятичасовой cadence, provider resets, routing, Byesu credentials, GPT Image contract, Krita preflight или vision gateway.

### Критерии готовности

- Startup с available state без ранее наблюдавшегося subscription limit не уведомляет.
- Повторный limited probe не создаёт новое recovery событие.
- Probe error, manual hold и наступление `codex_available_at` сами по себе не уведомляют.
- Velvet recovery при ещё limited Max не уведомляет; после подтверждённого восстановления обоих отправляется ровно одно сообщение.
- После restart main bot dedupe state не позволяет повторно отправить уже завершённое событие.
- Monitor не вызывает coder `/rate-limits` и не создаёт новый Telegram bot token/service.

### Риски и ограничения

- Telegram Bot API не предоставляет application-level idempotency key, поэтому durable marker закрывает штатные restart/retry дубли, но не может сделать сетевую отправку транзакционной вместе с локальным fsync.
- Production rollout и реальные Telegram/coder canary выполняются отдельно после merge через canonical update/orchestration path.
- На момент начала работы обязательный watcher tick `2026-08-08T04:29:43Z` ещё не наступил.

## После завершения

### Фактически сделано

- Добавлен `CodexRecoveryNotificationMonitor` в main Velvet application.
- Monitor использует существующие `CODEX_LIMITS_BASE_URL` и `CODEX_LIMITS_API_KEY`, читает только coder capabilities и не делает собственных live quota probes.
- Pool-level limited/recovery state хранится атомарно в `/app/runtime/codex-recovery-notifications.json` с mode `0600`.
- Одна recovery generation объединяет Velvet и Max: уведомление отправляется только после успешного recovery state обоих project и затем помечается persistent dedupe marker.
- Получателем является primary owner numeric chat id; при отсутствии numeric owner используется существующий log chat. Отправка идёт через тот же `Bot`, который создаёт основной application bootstrap.
- Добавлены regression tests для single-send, restart dedupe, staggered Velvet/Max recovery, probe error, startup без previous limit, manual hold и проверки отсутствия `/rate-limits` в monitor path.

### Миграции и совместимость

SQL migrations отсутствуют. Формат `/opt/codex-runs/codex-availability.json` не меняется. Новый bot runtime state создаётся лениво только после наблюдения реального subscription limit. Existing dynamic gate, пятичасовой watcher, reset-time probes и Byesu fallback semantics не меняются.

### Проверки

- Изолированный state-machine smoke: `RECOVERY_DEDUPE_OK`.
- Startup false-positive smoke: `NO_STARTUP_FALSE_POSITIVE_OK`.
- Probe-error smoke: `PROBE_ERROR_NO_NOTIFY_OK`.
- Полный protected CI должен подтвердить final PR head перед merge.

### PR и commit

- Ветка: `feat/codex-recovery-notification`
- Base: `8b160db820592c36f51da491b0525754f6954bdf`
- PR и exact tested head фиксируются GitHub после публикации этого focused diff.
- Merge разрешён только при `behind_by=0` и terminal success всех шести protected checks.

### Незавершённое

- Production пока не обновлён этим изменением.
- После merge требуется canonical `velvet update`, подтверждённый `operation.status=success`, clean checkout и `deploy/hermes-orchestration/install.sh` без обхода idle gate.
- После `2026-08-08T04:29:43Z` нужно отдельно проверить первый реальный пятичасовой watcher tick обоих project.
- Пока quota реально limited, требуется read-only Kael/coder smoke с `actual_route=Byesu` и subscription-limit evidence.
- После реального quota recovery требуется подтвердить automatic `false -> true`, одно Telegram recovery notification, затем Codex coder route и отдельные GPT Image 2 1K/2K/4K smokes по существующему contract.
- Krita server preflight и `velvet-vision-gateway-1` unhealthy остаются отдельными задачами и в этот diff не входят.

### Следующий шаг

Открыть focused PR, дождаться terminal success всех required checks, проверить актуальный main drift/behind status и merge только exact tested head. Production rollout выполнять отдельно по canonical contract после merge.
