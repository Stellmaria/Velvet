# Сессия: retirement legacy media delivery installers

- Дата: `2026-08-06`
- ID: `issue-457-retire-legacy-delivery-installers`
- Линия/фаза: `P0 media delivery / repository retirement`
- Ветка: `feat/457-retire-legacy-delivery-installers`
- Статус: `частично`
- Базовый commit: `7b561b0bb2d04b7d5fd4fa3ae084d9af830c424f`
- Связанные issue: `#457`, `#410`, `#412`, `#455`, `#458`, `#514`

## Перед началом

### Цель

Удалить четыре neutralized runtime installer, которые продолжали входить в startup graph после перехода на durable media delivery PR #488, и оставить один явный repository-side ownership contract без повторного provider submit, charge или Telegram send.

### Исходный контекст

PR #488 уже поставил durable media delivery repository, result resolver, download, independent original/preview outcomes, notification и redelivery. Issue #511 закрыла correctness blocker этого контура.

При этом current `main` продолжал:

- перечислять четыре legacy delivery stage в application composition;
- импортировать четыре legacy installer module;
- держать runtime `install_delivery_handler` mutation hook;
- нейтрализовать старые installer через `importlib` и присваивание `_INSTALLED = True`;
- сохранять отдельные image/video, Auf recovery и active-worker ownership layers рядом с каноническим durable runtime.

### Планируемый объём

- удалить `original_image_delivery_hotfix`;
- удалить `original_video_delivery_hotfix`;
- удалить `auf_result_delivery_recovery`;
- удалить `auf_active_delivery_fix`;
- убрать четыре stage/import/name из composition;
- удалить runtime `install_delivery_handler` hook;
- заменить magic `__getattribute__` interception явным no-op inherited delivery phase у active Friendly worker;
- сохранить canonical durable runtime и `media_delivery_ui_install`;
- обновить focused tests, generated inventories и canonical docs.

### Критерии готовности

- legacy modules физически отсутствуют;
- startup composition не содержит их stage/import/name;
- active worker не выполняет inherited best-effort Telegram delivery;
- redelivery path не имеет provider submit/charge boundary;
- canonical UI продолжает выдавать один result action;
- architecture inventories воспроизводимо уменьшаются;
- focused tests, project preflight и required PR CI проходят на exact head;
- live provider/Telegram acceptance не выдаётся за repository verification.

### Риски и ограничения

- удаление legacy delivery phase не должно вернуть duplicate Telegram send;
- наследуемый base worker method должен быть явно отключён, а не скрыт новым dynamic interception;
- existing transitional `Any` constructor contract не должен быть «исправлен» новым aiogram import в domain layer;
- PostgreSQL/provider/Telegram restart, CDN и expired URL acceptance невозможно выполнить без server/runtime access;
- issue #457 нельзя закрывать только по repository CI.

## После завершения

### Фактически сделано

- удалены четыре legacy delivery module;
- удалены четыре startup composition stage и связанные imports/names;
- удалён runtime `install_delivery_handler` mutation hook;
- удалены `importlib`, local installer sentinel и `_disable_legacy_delivery_installers` из Friendly worker;
- magic `__getattribute__` interception заменён явным `_deliver_best_effort(...)` no-op;
- durable repository/resolver/download/original/preview/notification/redelivery ownership сохранён;
- canonical `media_delivery_ui_install` сохранён;
- legacy UI tests перенесены на canonical module;
- image/video/recovery assertions перенесены с удалённых modules на `TelegramMediaDeliveryTransport` и durable use cases;
- package architecture, shared-contract, stability, repository-layout и Telegram navigation inventories пересобраны;
- production modules снижены `659 → 655`;
- startup installer stages снижены `25 → 21`;
- registered package violations снижены `537 → 521`;
- private cross-module accesses снижены `184 → 180`;
- exact/normalized duplicate groups снижены `68/98 → 66/95`;
- удалено 16 stale architecture exemptions.

### Миграции и совместимость

Database migrations и изменения persisted schema не требуются.

Compatibility сохраняется на behavioral boundary:

- provider completion по-прежнему сохраняется до delivery;
- active worker не отправляет результат через inherited legacy method;
- result action использует durable redelivery use case;
- повторная доставка не создаёт новый provider task, attempt или charge;
- external acceptance и rollback evidence остаются в #410/#412.

### Проверки

Branch maintenance на product diff успешно выполнил:

- 22 focused composition/durable-delivery/UI/worker tests;
- shared-contract inventory check;
- package architecture inventory write/check с canonical label;
- repository layout inventory write/check;
- Telegram navigation inventory check;
- project CI preflight;
- `git diff --check`.

PR required CI выполняется заново после этого worklog-only исправления. До merge обязательны green tests, type check, Docker, notes, security/supply-chain и branch-protection checks.

### PR и commit

- PR: `#662` — `P0: retire legacy media delivery installers`;
- ветка: `feat/457-retire-legacy-delivery-installers`;
- предыдущий exact head: `6db4eb1d601d185310ce761892bd9e9ef105878d`;
- новый exact head определяется commit этого worklog fix;
- squash merge commit в `main`: pending required CI и unchanged-head merge gate.

### Незавершённое

Без production/server access не выполнены:

- live Kie/GRS/photo/video provider matrix;
- Telegram/CDN outage and recovery;
- restart before/after provider success/download/partial delivery;
- expired/unrecoverable URL behavior;
- production no-double-submit/no-double-charge evidence;
- actual credits/cost/delivery timings.

Эти пункты остаются в #410/#412. Issue #457 после repository merge остаётся открытой только для внешней acceptance matrix.

### Следующий шаг

Дождаться required CI на новом exact head, проверить review threads и mergeability, затем выполнить squash merge PR #662 с SHA guard. После merge обновить #457 и #595 фактическим merge commit и оставить live acceptance открытой в #410/#412.
