# Сессия: явные presentation contracts watermark

- Дата: 2026-07-24
- ID: `2026-07-24-watermark-presentation-contracts`
- Линия/фаза: workspace architecture cleanup
- Статус: `частично`
- Ветка: `agent/watermark-presentation-contracts`
- Базовый commit: `20ff548be9cc3d759637869d4db566c022a2a87f`

## Перед началом

### Цель

Убрать runtime-подмены watermark formatter/keyboard и Krita wake policy из `install_workspace_product_experience()`.

### Исходный контекст

После переноса persistence в domain boundary workspace installer всё ещё подменял функции `watermark_ui`, импортированные функции core/service/public archive и `_wake_krita`. Draft-aware UI и правило отложенного запуска Krita существовали только благодаря порядку импортов и mutation глобальных объектов.

### Планируемый объём

- сделать `watermark_ui.build_watermark_keyboard()` канонически draft-aware;
- сделать `format_watermark_caption()` канонически draft/error-aware;
- добавить общий публичный `wake_krita()` contract;
- не запускать Krita при открытии формы и создании draft;
- явно запускать Krita при генерации или pending revision;
- удалить watermark UI/wake monkeypatch из workspace installer;
- добавить UI, wake-policy и architecture regression-тесты.

### Критерии готовности

- canonical UI корректно отображает draft, pending/processing, error и ready/archive состояния;
- workspace installer не присваивает функции в watermark modules;
- форма и создание draft не вызывают Supervisor;
- generate/public archive pending flows используют общий wake contract;
- полный CI зелёный.

### Риски и ограничения

Home keyboard, workspace render wrappers, quick references и callback prefix compatibility остаются в installer. Они относятся к отдельным workspace presentation срезам. Схема БД и persistence не меняются.

## После завершения

### Фактически сделано

- подготовлены checked transformations для canonical UI и общего Krita wake contract;
- добавлены UI, Supervisor и architecture regression-тесты.

### Миграции и совместимость

Миграции не требуются. Callback actions `generate` и `draft_noop` сохраняются. Ready/archive keyboards и прежние pending-вызовы service остаются совместимыми.

### Проверки

Focused и полный CI будут записаны после применения transformations.

### PR и commit

Ветка `agent/watermark-presentation-contracts`; PR создаётся после focused validation.

### Незавершённое

- применить transformations;
- выполнить focused tests;
- открыть PR и дождаться полного CI.

### Следующий шаг

После merge убрать оставшиеся cross-controller workspace UI monkeypatch небольшими отдельными срезами.
