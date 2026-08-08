# VL typed failures and bounded retries

- Дата: 2026-08-08
- ID: `2026-08-08-vl-typed-failures`
- Линия/фаза: Velvet AI / VL production safety / transport lifecycle
- Статус: `частично`
- Ветка: `fix/vl-typed-failures`
- Базовый commit: `86b276120fd7e260a16a78d83154c2ddaeac83bf`

Связано: #630, #709, #712, #718, #421.

## Перед началом

### Цель

Разделить VL failures на typed outcomes и прекратить бесконтрольный повтор полного image request. Timeout, cancellation, OOM, transport, provider error, invalid schema и refusal должны иметь разные semantics, а один local image не должен повторно уходить на 300-second inference только потому, что ошибка попала в общий `VisionProviderUnavailable`.

### Исходный контекст

Production `qwen3.5:9b` уже демонстрировал 300-second timeout при ~1.8-2.2 output tok/s. Старый `MeteredVisionClient` повторял любой `VisionProviderUnavailable` до route `max_attempts`, а global `QualityVisionClient` при invalid structured output мог повторно передать то же изображение в другом JSON mode. Вдобавок inference transport выполнялся через `asyncio.to_thread(urllib)`, поэтому cancellation Python task не гарантировала закрытие уже начатого HTTP request.

После #718 mass queue уже требует owner plan/start. Следующий safety layer должен сделать один конкретный inference предсказуемым до перехода к multi-model routing.

### Планируемый объём

- ввести typed failure taxonomy: `timeout`, `cancelled`, `transport`, `oom`, `provider_error`, `invalid_schema`, `refusal`;
- добавить cancellable aiohttp transport для VL POST requests;
- сохранить `asyncio.CancelledError` как cancellation, не превращать его в provider retry;
- ограничить full-image retry максимум двумя total attempts и только transient transport failure;
- timeout не replay-ить автоматически полным image request;
- OOM/schema/provider/refusal считать terminal для текущего full-image route;
- убрать automatic second-image JSON-mode fallback;
- перевести global quality client на тот же cancellable single-shot transport;
- сохранять typed terminal quality failures как permanent там, где это доказано;
- не увеличивать production timeout.

### Критерии готовности

- HTTP 504/timeout получает `timeout` и не вызывает automatic full-image replay;
- HTTP/Ollama OOM получает `oom` и не retry-ится;
- transient transport получает максимум один full-image retry;
- invalid structured output получает `invalid_schema` и не передаёт image повторно;
- provider refusal получает отдельный typed outcome для будущего uncensored route;
- task cancellation проходит наружу как `CancelledError`, aiohttp request context закрывается;
- global quality worker и manual quality используют cancellable client;
- required CI зелёный на актуальном main head.

### Риски и ограничения

- typed failures не являются разрешением на cloud fallback;
- timeout остаётся 300 seconds там, где он уже настроен, этот slice меняет semantics, а не число;
- text-only schema repair не добавляется автоматически: invalid schema сейчас останавливается terminal вместо повторной отправки изображения;
- provider-specific OOM detection основан на HTTP status/detail markers и должен дополняться по production evidence;
- semantic durable task queue может иметь собственный task-level retry lifecycle, который остаётся отдельным от immediate full-image retry transport;
- `AI_QUALITY_ENABLED=false` остаётся production default до single-target smoke.

### Стабилизационный допуск

1. Никакой новой модели и никакого cloud provider этот PR не включает.
2. Retry blast radius уменьшается: route max attempts больше не может превратить один request в пять full-image calls.
3. Existing public `VisionAnalysisError` / `VisionProviderUnavailable` catches продолжают работать через subclasses.
4. Cancellable HTTP применяется к routed VL и global/manual quality inference, где длинные requests наиболее опасны.
5. Следующий slice после merge остаётся 3-model routing по #630.

## После завершения

### Фактически сделано

- добавлен `velvet_bot/vision_failures.py` с typed failure taxonomy и retry/permanent helpers;
- добавлен `velvet_bot/vision_http.py` с aiohttp POST, real coroutine cancellation и typed HTTP/payload failures;
- `MeteredVisionClient` больше не использует `to_thread` для inference HTTP;
- immediate full-image attempt limit hard-capped at 2 независимо от более высокого route max attempts;
- только `VisionTransportError` допускает один immediate full-image retry;
- `VisionTimeoutError` typed transient, но full-image replay запрещён;
- OOM/provider/schema/refusal не replay-ятся;
- structured-output failure больше не включает второй image request с другим JSON mode;
- добавлен `TypedQualityVisionClient` для global/manual quality;
- calibrated quality persistence использует typed permanent classification;
- wiring global/manual quality выполняется отдельным deterministic helper commit в этом PR;
- unit coverage добавлена для timeout/OOM/transport/schema/cancellation и retry bounds.

### Проверки

- targeted typed-failure tests добавлены;
- существующие metered client/refusal contracts сохраняются через subclass compatibility;
- required project CI должен быть зелёным на финальном head до merge.

### PR и commit

- PR будет создан из `fix/vl-typed-failures` в `main`;
- merge SHA будет добавлен после зелёного CI.

### Незавершённое

- получить automatic wiring commit из temporary PR workflow и удалить helper workflow;
- исправить реальные CI regressions;
- слить PR только после required green checks;
- production `AI_QUALITY_ENABLED=false` не менять этим PR;
- после merge продолжить 3-model runtime/router #630.

### Следующий шаг

Создать PR, дождаться deterministic wiring global/manual quality client, затем прогнать required CI. После зелёного merge перейти к runtime model routing без возврата к массовым retries.
