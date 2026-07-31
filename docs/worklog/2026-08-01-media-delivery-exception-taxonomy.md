# 2026-08-01 — Typed failures и claim compensation media delivery

- Дата: `2026-08-01`
- ID: `media-delivery-exception-taxonomy`
- Issue: `#511`
- Линия/фаза: `P0 correctness hardening`
- Статус: `завершено`
- Ветка: `agent/harden-media-delivery-exceptions`
- Базовый commit: `07a935425abf72c38f0b0f2e25f3fed982fa05a5`

## Перед началом

### Цель

Закрыть unresolved broad exceptions в correctness-critical контуре оплаченных генераций: отделить временные ошибки транспорта от terminal validation и programming failures, гарантировать компенсацию claimed job и исключить автоматическую повторную отправку Telegram после неоднозначного исхода.

### Исходный контекст

Generated P2 inventory фиксировал 11 широких catches в пяти media-delivery файлах. `DeliverMediaResult` обрабатывал download, original, preview, direct preview и notification отдельными `except Exception`, сохранял `str(error)` и не имел симметричного outer compensation для ошибок repository transition.

Особенно опасно окно между фактической отправкой Telegram и `mark_channel(SUCCESS)`: если сообщение уже принято Telegram, а запись состояния упала, следующий recovery видел старый `pending/failed` и мог повторно отправить оригинал или preview. Иными словами, распределённая транзакция пыталась притворяться обычной функцией. Это редко заканчивается достойно.

### Планируемый объём

- добавить typed taxonomy `transient / terminal / programming`;
- хранить redacted code/fingerprint отдельно от безопасного human message;
- запретить raw provider URL, Telegram identifiers и user content в durable errors;
- добавить состояние `uncertain` перед фактической Telegram send;
- не повторять автоматически канал с `uncertain`, пока отсутствует подтверждённая необходимость;
- сделать channel/job transitions монотонными;
- добавить outer compensation для claimed delivery и resolution jobs;
- не поглощать `TypeError`, invariant violations и неизвестные programming failures;
- классифицировать broad boundaries явными P2 annotations;
- добавить fault-injection tests для send/state/finish failures;
- обновить P2, shared-contract и package-architecture inventories.

### Критерии готовности

- unresolved broad exceptions в media-delivery контуре равны нулю;
- programming error компенсирует claim и повторно выбрасывается;
- send success + state failure не приводит к duplicate channel delivery;
- finish failure после успешных channels не приводит к повторной отправке;
- durable error payload не содержит исходный текст исключения;
- migration добавляет structured fields и `uncertain` state;
- tests, type check, Docker build, project notes и architecture gates зелёные;
- PR синхронизирован с актуальным `main` перед merge.

### Риски и ограничения

`uncertain` намеренно выбирает at-most-once поведение для неоднозначной Telegram send: автоматический worker не дублирует сообщение, которое могло быть доставлено. Ручная redelivery владельца сбрасывает состояние осознанно и остаётся отдельным действием без provider submit и charge.

Legacy delivery installers нельзя удалить в этом срезе без лжи в dependency graph: `auf_generation_receipt_install.py` всё ещё использует их для receipt/caption compatibility. Их retirement остаётся в #457/#455 после переноса активных consumers.

## После завершения

### Фактически сделано

- добавлен `media_delivery_errors.py` с typed classification и стабильным fingerprint;
- durable errors сериализуются как безопасный structured JSON без исходного сообщения;
- migration `z030` добавляет error code/fingerprint и `uncertain` channel state;
- Telegram channels и notification переходят в `uncertain` до внешнего send;
- успешные/expired transitions нельзя понизить поздним failure update;
- outer compensation освобождает claim в retry/failed state, а при недоступной БД остаётся существующий stale-lease recovery;
- provider result resolver использует typed pending/failed outcomes;
- queue/runtime boundaries логируют только code/fingerprint и повторно выбрасывают programming errors;
- добавлены fault-injection tests send-before-state, finish-after-send и redaction.

### Миграции и совместимость

`z030_media_delivery_failure_taxonomy.sql` является additive migration. Existing rows остаются совместимыми; новые code/fingerprint columns nullable. Check constraints расширены значением `uncertain` только для внешних send channels и notification.

### Проверки

- P2 inventory schema `75` пересобран от актуального `main`;
- `broad_exception_total = 102`;
- `broad_exception_approved = 102`;
- `broad_exception_unresolved = 0`;
- shared-contract и package-architecture inventories пересобраны;
- Telegram navigation inventory пересобран: `631` Python-файл, `1049` inline-кнопок, `0` нарушений;
- canonical `development_status`, `project_memory` и `ARCHITECTURE_AUDIT` синхронизированы с generated baseline;
- временные scripts/workflows удалены из ветки;
- финальная GitHub Actions матрица запускается на владельческом commit.

### PR и commit

- PR: `#531 Закрыть broad exceptions и duplicate window media delivery`;
- prerequisite/current base: `07a935425abf72c38f0b0f2e25f3fed982fa05a5`;
- финальный squash SHA будет добавлен в issue после merge.

### Незавершённое

Live acceptance остаётся в #410/#412: Telegram outage, provider sandbox и фактическая redelivery на production VPS. Retirement legacy installers остаётся #457/#455, поскольку активные receipt consumers ещё не мигрированы.

### Следующий шаг

Пройти финальный CI, проверить review threads и слить PR squash-коммитом в `main`.
