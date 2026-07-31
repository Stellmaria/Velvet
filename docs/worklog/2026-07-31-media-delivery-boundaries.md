# 2026-07-31 — Typed boundaries durable media delivery

- Дата: `2026-07-31`
- ID: `media-delivery-boundaries`
- Линия/фаза: `P2 stability / paid media delivery`
- Статус: `завершено`
- Ветка: `agent/issue-511-media-delivery-boundaries`
- Базовый commit: `31a8a0b496a3b3e95fb6b03f23867907884554d3`

## Перед началом

### Цель

Закрыть 11 unresolved broad exceptions в durable media delivery и устранить автоматический дубль Telegram-доставки, возможный при успешной отправке с последующим отказом PostgreSQL.

### Исходный контекст

Пять файлов media delivery ловили `Exception` вокруг transport, provider resolution, queue integration, recovery worker и redelivery UI. В `DeliverMediaResult` Telegram side effect выполнялся до записи `success`; если `mark_channel` или `finish` падали после фактической отправки, следующий worker видел канал как pending/failed и мог отправить тот же оплаченный результат повторно.

Ошибки провайдера, Telegram, PostgreSQL, cancellation и programming bugs попадали в одинаковые catch-all ветки. Пользовательский callback получал усечённый `str(error)`, который мог содержать внутренний provider или infrastructure context.

### Планируемый объём

- ввести typed transport/provider/repository/state-conflict errors;
- добавить machine-readable error code, retryable и безопасный public message;
- записывать `sending` до Telegram side effect;
- записывать `uncertain`, если Telegram call завершился, но фиксация success не удалась;
- не повторять автоматически `sending/uncertain` каналы;
- сделать SQL transitions monotonic и проверять `UPDATE 1`;
- сохранить explicit redelivery как единственный способ сбросить ambiguous state;
- разделить provider pending и terminal result;
- пробрасывать cancellation и programming errors;
- обновить migration, tests и generated P2/package inventories.

### Критерии готовности

- в пяти целевых файлах нет unresolved broad catches;
- transport failures ловятся только через typed adapter contract;
- repository failures не маскируются под transport retry;
- перед каждым Telegram send в PostgreSQL зафиксирован `sending`;
- post-send persistence failure становится `uncertain` либо оставляет `sending`;
- reclaimed worker не отправляет ambiguous channel повторно;
- raw `TypeError` не превращается в retry;
- provider pending retryable, provider terminal не retryable;
- пользователь не получает raw provider/SQL error;
- full CI matrix зелёный.

### Риски и ограничения

Telegram Bot API не предоставляет idempotency key для `send_document`, `send_photo` и `send_video`. Поэтому после ambiguous side effect система не может доказать отсутствие доставки. Выбран fail-closed контракт: automatic retry блокируется, job завершается partial/failed, а владелец может выполнить explicit redelivery, которая сознательно сбрасывает состояния.

## После завершения

### Фактически сделано

Добавлена иерархия `MediaDeliveryError`: transport, provider, repository, state conflict и runtime unavailable. Ошибки имеют стабильный code, retryable и public message; сырой exception хранится только в protected log через exception chaining.

Telegram adapter переводит HTTP/download и Telegram API failures в typed transport errors. Provider resolver различает pending и terminal состояния сохранённой оплаченной задачи. PostgreSQL repository получил единый adapter boundary, а finish/channel/notification transitions проверяют ownership и affected row.

В migration `z030_media_delivery_uncertain_states.sql` добавлены `sending` и `uncertain` для original, preview и notification. Use case сохраняет `sending` до side effect, переводит transport failure в `failed`, success в `success`, а отказ persistence после send в `uncertain`. Cancellation во время Telegram call также считается ambiguous.

Queue, friendly recovery worker и redelivery callback ловят только expected typed failures. Programming errors не маскируются. Пользователь видит безопасное описание без provider/SQL payload.

### Миграции и совместимость

Добавлена additive migration `z030_media_delivery_uncertain_states.sql`, которая расширяет CHECK constraints существующих status columns. Таблицы и данные не пересоздаются.

Existing pending/failed/success/expired/skipped rows остаются валидными. Explicit redelivery по-прежнему сбрасывает item и notification states в pending. Старые API use cases сохраняют сигнатуры; `MediaDeliverySummary` получил дополнительный `uncertain_channels` с default 0.

### Проверки

Добавлены regression tests для:

- `sending → failed` при transport failure;
- `sending → success → uncertain` при post-send repository failure;
- отсутствия automatic resend для reclaimed `sending` channel;
- проброса raw programming `TypeError`;
- provider pending retry и provider terminal stop;
- migration contract `sending/uncertain`;
- отсутствия `except Exception` в пяти целевых файлах;
- сохранения legacy worker delivery guard.

Generated P2 stability, shared-contract и package architecture inventories пересобраны в полном GitHub Actions checkout и зафиксированы в ветке.

### PR и commit

- Issue: `#511`
- PR: `#523`
- Ветка: `agent/issue-511-media-delivery-boundaries`
- Основные commits: connector-backed commits ветки и итоговый squash commit после merge.

### Незавершённое

До merge требуется получить зелёные tests/type-check/docker-build/project-notes/backup-drill checks. После merge нужен VPS smoke на одном тестовом result: normal success, simulated Telegram rejection и controlled database failure до фактической production нагрузки.

### Следующий шаг

Получить чистый финальный matrix, слить PR и выполнить live acceptance без повторного запуска provider generation.

### Итоговые generated metrics

- Broad exceptions: 89 total, 89 approved, 0 unresolved in 0 files.
- Package architecture: 629 modules, 136259 LOC, 546 reviewed violations/exemptions.
- Shared contracts: 629 files, 3597 functions, 182 transitional private accesses, 0 blocking contracts.
